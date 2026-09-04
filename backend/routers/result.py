"""
結果操作ルーター

OCR処理結果の取得・修正・確認・ダウンロードを行うAPIエンドポイント群。
"""

import asyncio
import io
import logging
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.models.audit import AuditEventType
from backend.models.enums import BatchFileStatus, DocumentStatus
from backend.models.schemas import (
    ConfirmRequest,
    FieldUpdateRequest,
    OcrDocument,
    OcrField,
    VisualCheck,
    VisualCheckUpdateRequest,
)
from backend.services.audit_logger import log_event
from backend.services.auth import AuthenticatedUser, get_current_user
from backend.services.batch_store import batch_store
from backend.services.csv_generator import CsvGenerator
from backend.services.pdf_renamer import PdfRenamer
from backend.services.s3_storage import s3_storage
from backend.services.store import store

# ルーター全体に認証を要求する（個別エンドポイントでの記述を省略できる）
router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)

# サービスインスタンス
_csv_generator = CsvGenerator()
_pdf_renamer = PdfRenamer()


@router.get("/result/{file_id}", response_model=OcrDocument)
async def get_result(file_id: str):
    """OCR処理結果取得"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")
    return document


@router.put("/result/{file_id}/fields", response_model=OcrField)
async def update_field(file_id: str, request: FieldUpdateRequest):
    """フィールド修正（値修正 or チェックステータス変更）"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    # check_statusのバリデーション
    valid_statuses = {"ok", "ng", "needs_review", None}
    if request.check_status is not None and request.check_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"check_statusは 'ok', 'ng', 'needs_review' のいずれかを指定してください",
        )

    for field in document.fields:
        if field.field_name == request.field_name:
            # 値の修正がある場合
            if request.corrected_value is not None:
                field.corrected_value = request.corrected_value
                field.is_confirmed = True
            # チェックステータスの変更がある場合
            if request.check_status is not None:
                field.manual_check_status = request.check_status
                field.is_confirmed = True
            document.updated_at = datetime.now()

            # 全フィールドのステータスを確認してドキュメント全体のステータスを再評価
            _reevaluate_document_status(document, file_id)

            store.update(document)
            return field

    raise HTTPException(
        status_code=404,
        detail=f"フィールド '{request.field_name}' が見つかりません",
    )


def _reevaluate_document_status(document: OcrDocument, file_id: str) -> None:
    """
    全フィールドの手動チェックステータスに基づいてドキュメント＆バッチファイルの状態を再評価する。
    全フィールドがOK → 完了、1つでもNG/確認必要 → 確認必要のまま。
    """
    # 排他フィールド判定用
    bank_fields = {'銀行名', '支店名', '預金種目', '口座番号', '銀行番号', '店番号'}
    yucho_fields = {'ゆうちょ記号', 'ゆうちょ番号'}

    has_yucho = any(
        f.value for f in document.fields if f.field_name in yucho_fields
    )
    has_bank = any(
        f.value for f in document.fields if f.field_name in bank_fields
    )

    all_ok = True
    for f in document.fields:
        # 排他フィールドで対象外の場合はスキップ
        if f.field_name in bank_fields and has_yucho and not has_bank:
            continue
        if f.field_name in yucho_fields and has_bank and not has_yucho:
            continue

        # manual_check_statusが設定されている場合はそれで判定
        if f.manual_check_status:
            if f.manual_check_status != "ok":
                all_ok = False
                break
        else:
            # 手動ステータス未設定の場合は自動判定
            if not f.value:
                all_ok = False
                break
            if f.confidence_level.value == "low":
                all_ok = False
                break
            if f.master_match and f.master_match.match_status == "ng":
                all_ok = False
                break
            if f.master_match and f.master_match.cross_check_status == "mismatch":
                all_ok = False
                break

    # ドキュメントステータス更新
    if all_ok:
        document.status = DocumentStatus.NORMAL
    else:
        document.status = DocumentStatus.NEEDS_REVIEW

    # バッチファイルステータス更新
    batch_id, file_item = batch_store.find_batch_by_file_id(file_id)
    if batch_id and file_item:
        if all_ok:
            batch_store.update_file_status(batch_id, file_id, BatchFileStatus.COMPLETED)
        else:
            batch_store.update_file_status(batch_id, file_id, BatchFileStatus.NEEDS_REVIEW)

        # S3のExcelを最新データで再生成・上書き保存（バックグラウンド）
        asyncio.create_task(_update_s3_excel(batch_id))


async def _update_s3_excel(batch_id: str) -> None:
    """バッチのExcelファイルをS3に上書き保存する（既存キーを再利用）"""
    try:
        from backend.routers.batch import _build_csv_row

        job = batch_store.get_job(batch_id)
        if not job:
            return

        # 既存のS3キーがない場合は何もしない
        if not job.s3_output_key:
            return

        rows = []
        for file_item in job.files:
            if file_item.status in (
                BatchFileStatus.COMPLETED,
                BatchFileStatus.NEEDS_REVIEW,
            ):
                doc = store.get(file_item.file_id)
                if doc:
                    rows.append(_build_csv_row(doc, file_item))

        if rows:
            excel_bytes = _csv_generator.generate_excel(rows)
            # 既存のS3キーに上書き
            await asyncio.to_thread(
                s3_storage.overwrite_output_excel, job.s3_output_key, excel_bytes
            )
            logger.info(f"[バッチ {batch_id}] S3 Excel上書き完了: {job.s3_output_key}")

    except Exception as e:
        logger.error(f"[バッチ {batch_id}] S3 Excel上書き失敗: {e}")


@router.put("/result/{file_id}/visual-checks", response_model=VisualCheck)
async def update_visual_check(file_id: str, request: VisualCheckUpdateRequest):
    """目視確認ステータス更新"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    for check in document.visual_checks:
        if check.check_item == request.check_item:
            check.is_checked = request.is_checked
            check.checked_by = request.checked_by
            check.checked_at = datetime.now() if request.is_checked else None
            document.updated_at = datetime.now()
            store.update(document)
            return check

    raise HTTPException(
        status_code=404,
        detail=f"確認項目 '{request.check_item}' が見つかりません",
    )


@router.post("/result/{file_id}/confirm", response_model=OcrDocument)
async def confirm_document(file_id: str, request: ConfirmRequest):
    """確認完了処理"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    document.confirmed_at = datetime.now()
    document.confirmed_by = request.confirmed_by
    document.updated_at = datetime.now()
    store.update(document)
    return document


@router.get("/result/{file_id}/csv")
async def download_csv(
    file_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """CSV生成・ダウンロード"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    # 監査ログ: 結果ダウンロード
    log_event(
        AuditEventType.RESULT_DOWNLOAD,
        request=request,
        user_email=current_user.email,
        user_groups=current_user.groups,
        target_file=document.original_filename or file_id,
        detail="download=csv",
    )

    csv_bytes = _csv_generator.generate(document)
    filename = _csv_generator.generate_filename(document)
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=shift_jis",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )


@router.get("/result/{file_id}/pdf-preview")
async def preview_pdf(file_id: str):
    """PDFプレビュー表示用エンドポイント（inline表示）"""
    pdf_bytes = store.get_pdf(file_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDFファイルが見つかりません")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline"
        },
    )


@router.get("/result/{file_id}/pdf")
async def download_pdf(
    file_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """リネーム済みPDFダウンロード"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    pdf_bytes = store.get_pdf(file_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDFファイルが見つかりません")

    # 監査ログ: 結果ダウンロード
    log_event(
        AuditEventType.RESULT_DOWNLOAD,
        request=request,
        user_email=current_user.email,
        user_groups=current_user.groups,
        target_file=document.original_filename or file_id,
        detail="download=pdf",
    )

    _, filename = _pdf_renamer.rename(pdf_bytes, document)
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )
