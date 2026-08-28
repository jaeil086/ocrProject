"""
アップロードルーター

POST /api/upload: PDFファイルアップロード + 自動OCR処理
複数ページPDFは自動的にページ単位で分割し、各ページを独立処理する。
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.models.enums import DocumentStatus, VisualCheckType
from backend.models.schemas import (
    OcrDocument,
    UploadResponse,
    VisualCheck,
)
from backend.services.document_classifier import DocumentClassifier
from backend.services.ocr_pipeline import OcrPipeline
from backend.services.pdf_reader import PdfReader
from backend.services.store import store
from backend.services.validator import Validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# サービスインスタンス生成
_validator = Validator()
_classifier = DocumentClassifier()
_ocr_pipeline = OcrPipeline()
_pdf_reader = PdfReader()


def _generate_file_id() -> str:
    """FileID採番（UUID4の先頭8文字）"""
    return str(uuid.uuid4())[:8]


def _generate_visual_checks() -> list[VisualCheck]:
    """デフォルト目視確認項目を生成する"""
    return [
        VisualCheck(
            check_item="金融機関お届け印",
            check_type=VisualCheckType.SEAL,
        ),
        VisualCheck(
            check_item="銀行・信用金庫・組合の選択",
            check_type=VisualCheckType.CIRCLE_MARK,
        ),
        VisualCheck(
            check_item="預金種目の選択",
            check_type=VisualCheckType.CIRCLE_MARK,
        ),
        VisualCheck(
            check_item="収納代行会社",
            check_type=VisualCheckType.AGENCY_CHECK,
        ),
    ]


def _validate_pdf_format(file: UploadFile) -> None:
    """PDFファイル形式の検証"""
    is_pdf_content_type = file.content_type == "application/pdf"
    filename = file.filename or ""
    is_pdf_extension = filename.lower().endswith(".pdf")

    if not is_pdf_content_type and not is_pdf_extension:
        raise HTTPException(
            status_code=400,
            detail="PDF形式のファイルを選択してください",
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(files: list[UploadFile] = File(...)):
    """PDFファイルアップロード + 自動OCR処理（複数対応）

    複数ページのPDFファイルは自動的にページ単位で分割し、
    各ページを独立した預金口座振替届出書として処理する。
    """
    # 全ファイルのPDF形式を事前検証
    for file in files:
        _validate_pdf_format(file)

    results: list[dict] = []

    for file in files:
        original_filename = file.filename or "unknown.pdf"

        # PDFバイナリ読み込み
        pdf_bytes = await file.read()

        # PDF分割（複数ページの場合は各ページを個別PDFに分離）
        try:
            page_pdfs = await asyncio.to_thread(
                _pdf_reader.split_pages, pdf_bytes
            )
        except Exception as e:
            logger.warning(
                f"PDF分割失敗（元ファイルのまま処理続行）: {original_filename}: {e}"
            )
            page_pdfs = [pdf_bytes]

        total_pages = len(page_pdfs)

        # 各ページ（または分割なしの1ファイル）を個別に処理
        for page_num, page_pdf in enumerate(page_pdfs, start=1):
            # FileID採番
            file_id = _generate_file_id()

            # 表示用ファイル名: 複数ページの場合は「元ファイル名_p{ページ番号}」
            if total_pages > 1:
                base_name = original_filename
                if base_name.lower().endswith(".pdf"):
                    base_name = base_name[:-4]
                display_filename = f"{base_name}_p{page_num}.pdf"
            else:
                display_filename = original_filename

            logger.info(
                f"[{file_id}] 処理開始: {display_filename}"
                + (f" (元ファイル: {original_filename}, ページ {page_num}/{total_pages})"
                   if total_pages > 1 else "")
            )

            # OCRパイプライン実行
            processing_result = await _ocr_pipeline.process(file_id, page_pdf)

            document = processing_result.document
            document.original_filename = display_filename

            if not processing_result.success:
                # OCR処理失敗時
                document.status = DocumentStatus.PROCESSING
                store.save(document, page_pdf)
                results.append({
                    "file_id": file_id,
                    "original_filename": display_filename,
                    "status": document.status.value,
                    "fields": [],
                    "errors": [{"message": processing_result.error_message}],
                })
                continue

            # バリデーション実行
            # 銀行番号/店番号の桁数チェック・入れ替わり修正
            _validator.fix_swapped_bank_branch_codes(document.fields)
            # ゆうちょ記号/番号の桁数チェック・区切り修正
            _validator.fix_yucho_codes(document.fields)

            if document.form_type:
                missing_errors = _validator.check_missing_fields(
                    document.fields, document.form_type
                )
            else:
                missing_errors = []

            financial_errors = await _validator.check_financial_codes(document.fields)

            all_errors = missing_errors + financial_errors
            document.validation_errors = all_errors

            # 書類仕分け
            document.status = _classifier.classify(
                document.fields, document.validation_errors
            )

            # VisualCheck項目生成
            document.visual_checks = _generate_visual_checks()

            # InMemoryStore保存
            store.save(document, page_pdf)

            logger.info(
                f"[{file_id}] 処理完了: status={document.status.value}, "
                f"errors={len(all_errors)}"
            )

            # レスポンスデータ構築
            results.append({
                "file_id": file_id,
                "original_filename": display_filename,
                "status": document.status.value,
                "fields": [
                    {
                        "field_name": f.field_name,
                        "value": f.value,
                        "confidence_score": f.confidence_score,
                        "confidence_level": f.confidence_level.value,
                        "is_confirmed": f.is_confirmed,
                    }
                    for f in document.fields
                ],
                "errors": [
                    {
                        "field_name": e.field_name,
                        "error_type": e.error_type.value,
                        "message": e.message,
                    }
                    for e in document.validation_errors
                ],
            })

    return UploadResponse(files=results, total_count=len(results))
