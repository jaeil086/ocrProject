"""
バッチ処理ルーター

POST /api/batch/upload: 複数PDFファイルの一括アップロード + バックグラウンド処理開始
GET  /api/batch/{batch_id}/status: バッチ処理状況取得
POST /api/batch/{batch_id}/files/{file_id}/reprocess: 個別ファイル再処理
GET  /api/batch/{batch_id}/download/csv: 全体結果CSVダウンロード
GET  /api/batch/{batch_id}/download/zip: 全原本PDFのZIPダウンロード
"""

import asyncio
import io
import logging
import urllib.parse
import uuid
from datetime import datetime
import zipfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.models.enums import (
    BatchFileStatus,
    BatchJobStatus,
    ConfidenceLevel,
    DocumentStatus,
    VisualCheckType,
)
from backend.models.schemas import (
    BatchFileItem,
    BatchStatusResponse,
    BatchUploadResponse,
    OcrDocument,
    VisualCheck,
)
from backend.services.batch_store import batch_store
from backend.services.csv_generator import CsvGenerator
from backend.services.document_classifier import DocumentClassifier
from backend.services.ocr_pipeline import OcrPipeline
from backend.services.pdf_reader import PdfReader
from backend.services.s3_storage import s3_storage
from backend.services.store import store
from backend.services.validator import Validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch")

# サービスインスタンス
_csv_generator = CsvGenerator()
_validator = Validator()
_classifier = DocumentClassifier()
_ocr_pipeline = OcrPipeline()
_pdf_reader = PdfReader()

# バッチ処理の最大ファイル数
MAX_BATCH_FILES = 100
# 並行処理数（Bedrock APIレート制限を考慮）
CONCURRENT_LIMIT = 3
# CONCURRENT_LIMIT = 1


def _generate_file_id() -> str:
    """FileID採番（UUID4の先頭8文字）"""
    return str(uuid.uuid4())[:8]


def _generate_batch_id() -> str:
    """バッチジョブID採番"""
    return str(uuid.uuid4())[:12]


def _generate_batch_filename(seq: int, consignor: str, contract: str) -> str:
    """バッチ命名規則に基づくファイル名を生成する

    形式: {連番3桁}_{委託者番号}_{契約者番号}.pdf
    例: 001_11137_10110.pdf
    """
    seq_str = str(seq).zfill(3)
    consignor_str = consignor or "unknown"
    contract_str = contract or "unknown"
    return f"{seq_str}_{consignor_str}_{contract_str}.pdf"


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
            detail=f"PDF形式のファイルを選択してください: {filename}",
        )


async def _process_single_file(
    batch_id: str, file_id: str, pdf_bytes: bytes
) -> None:
    """単一ファイルのOCR処理を実行する（バックグラウンドタスク用）"""
    try:
        # ステータスを処理中に更新（progress: 5%）
        batch_store.update_file_status(
            batch_id, file_id, BatchFileStatus.PROCESSING
        )
        batch_store.update_file_progress(batch_id, file_id, 5)
        batch_store.add_file_log(batch_id, file_id, "OCR処理開始")

        # イベントループに制御を戻す（ポーリング応答を可能にする）
        await asyncio.sleep(0)

        # progress: 10% — PDF読み込み開始
        batch_store.update_file_progress(batch_id, file_id, 10)

        # OCRパイプライン実行（内部でステップごとにprogressを更新）
        batch_store.add_file_log(batch_id, file_id, "Claude Sonnet 4 OCR実行中")
        processing_result = await _ocr_pipeline.process(
            file_id, pdf_bytes,
            progress_callback=lambda p: batch_store.update_file_progress(batch_id, file_id, p),
        )

        # イベントループに制御を戻す
        await asyncio.sleep(0)

        document = processing_result.document
        # original_filenameを復元（store内のファイルアイテムから取得）
        file_item = batch_store.get_file_item(batch_id, file_id)
        if file_item:
            document.original_filename = file_item.original_filename

        if not processing_result.success:
            # OCR処理失敗
            document.status = DocumentStatus.PROCESSING
            store.save(document, pdf_bytes)
            batch_store.update_file_status(
                batch_id,
                file_id,
                BatchFileStatus.FAILED,
                error_message=processing_result.error_message,
            )
            batch_store.add_file_log(
                batch_id,
                file_id,
                f"OCR処理失敗: {processing_result.error_message}",
                level="error",
            )
            return

        # バリデーション実行（progress: 85%）
        batch_store.update_file_progress(batch_id, file_id, 85)
        batch_store.add_file_log(batch_id, file_id, "バリデーション実行中")

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
        store.save(document, pdf_bytes)

        # バッチファイルステータス判定
        if document.status == DocumentStatus.NEEDS_REVIEW:
            batch_file_status = BatchFileStatus.NEEDS_REVIEW
        elif document.status == DocumentStatus.DEFICIENT:
            batch_file_status = BatchFileStatus.NEEDS_REVIEW
        else:
            batch_file_status = BatchFileStatus.COMPLETED

        # 委託者番号・契約者番号を取得してバッチファイル名を更新（progress: 95%）
        batch_store.update_file_progress(batch_id, file_id, 95)
        consignor = document.consignor_number or ""
        contract = document.contract_number or ""

        batch_store.update_file_status(
            batch_id,
            file_id,
            batch_file_status,
            consignor_number=consignor or None,
            contract_number=contract or None,
        )

        # 完了（progress: 100%）
        batch_store.update_file_progress(batch_id, file_id, 100)

        # バッチファイル名を更新（OCR結果から番号が判明した場合）
        if file_item and (consignor or contract):
            new_batch_filename = _generate_batch_filename(
                file_item.seq_number, consignor, contract
            )
            batch_store.update_file_batch_filename(
                batch_id, file_id, new_batch_filename
            )

        batch_store.add_file_log(batch_id, file_id, "処理完了")
        logger.info(
            f"[バッチ {batch_id}][{file_id}] 処理完了: status={batch_file_status.value}"
        )

    except Exception as e:
        logger.error(
            f"[バッチ {batch_id}][{file_id}] 処理中に予期しないエラー: {e}"
        )
        batch_store.update_file_status(
            batch_id,
            file_id,
            BatchFileStatus.FAILED,
            error_message=str(e),
        )
        batch_store.add_file_log(
            batch_id, file_id, f"予期しないエラー: {e}", level="error"
        )


async def _upload_input_to_s3(
    batch_id: str, pdf_files: list[tuple[str, bytes]]
) -> None:
    """入力PDFをZIP化してS3にアップロードする（バックグラウンド実行）"""
    try:
        await asyncio.to_thread(
            s3_storage.upload_input_zip, batch_id, pdf_files
        )
    except Exception as e:
        logger.error(f"[バッチ {batch_id}] S3入力ZIPアップロード失敗: {e}")


async def _process_batch(
    batch_id: str, file_data_list: list[tuple[str, bytes]]
) -> None:
    """バッチ全体の処理を実行する（セマフォで並行数制限）"""
    # 最初のポーリングリクエストが先に処理されるよう、少し待つ
    await asyncio.sleep(0.1)

    batch_store.start_processing(batch_id)

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

    async def process_with_limit(file_id: str, pdf_bytes: bytes) -> None:
        async with semaphore:
            # 各ファイル処理前にイベントループに制御を戻す
            await asyncio.sleep(0)
            await _process_single_file(batch_id, file_id, pdf_bytes)

    # 全ファイルの並行処理を起動
    tasks = [
        asyncio.create_task(process_with_limit(file_id, pdf_bytes))
        for file_id, pdf_bytes in file_data_list
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"[バッチ {batch_id}] 全ファイル処理完了")

    # 全ファイル処理完了後、結果をS3に自動保存
    await _save_results_to_s3(batch_id)


async def _save_results_to_s3(batch_id: str) -> None:
    """バッチ処理完了後、結果Excel・アーカイブZIPをS3に自動保存する"""
    try:
        job = batch_store.get_job(batch_id)
        if not job:
            return

        output_key = None
        archive_key = None

        # --- 01_output: 全体結果Excelを生成して保存 ---
        rows = []
        for file_item in job.files:
            if file_item.status in (
                BatchFileStatus.COMPLETED,
                BatchFileStatus.NEEDS_REVIEW,
            ):
                document = store.get(file_item.file_id)
                if document:
                    rows.append(_build_csv_row(document, file_item))

        if rows:
            excel_bytes = _csv_generator.generate_excel(rows)
            output_key = await asyncio.to_thread(
                s3_storage.upload_output_excel, batch_id, excel_bytes
            )

        # --- 02_archive: 全原本PDFのZIPを生成して保存 ---
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_item in job.files:
                pdf_bytes = store.get_pdf(file_item.file_id)
                if pdf_bytes:
                    zf.writestr(file_item.batch_filename, pdf_bytes)
        zip_buffer.seek(0)

        if zip_buffer.getbuffer().nbytes > 22:
            archive_key = await asyncio.to_thread(
                s3_storage.upload_archive_zip, batch_id, zip_buffer.getvalue()
            )

        # S3キーをバッチジョブに記録
        batch_store.set_s3_keys(batch_id, output_key=output_key, archive_key=archive_key)

        logger.info(f"[バッチ {batch_id}] S3自動保存完了（結果Excel + アーカイブZIP）")

    except Exception as e:
        logger.error(f"[バッチ {batch_id}] S3自動保存失敗: {e}")


@router.post("/upload", response_model=BatchUploadResponse)
async def batch_upload(
    files: list[UploadFile] = File(...),
):
    """複数PDFファイルの一括アップロード + バックグラウンド処理開始

    複数ページのPDFファイルは自動的にページ単位で分割し、
    各ページを独立した預金口座振替届出書として処理する。
    """
    # ファイル数チェック
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"アップロード可能なファイル数は最大{MAX_BATCH_FILES}件です（{len(files)}件選択されています）",
        )

    if len(files) == 0:
        raise HTTPException(
            status_code=400,
            detail="ファイルが選択されていません",
        )

    # 全ファイルのPDF形式を事前検証
    for file in files:
        _validate_pdf_format(file)

    # ファイル読み込み + 複数ページPDF分割
    # (元ファイル名, 分割後PDFバイナリ, ページ番号, 元PDF総ページ数) のリスト
    split_items: list[tuple[str, bytes, int, int]] = []

    for file in files:
        original_filename = file.filename or "unknown.pdf"
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
            # 分割失敗時はそのまま1ファイルとして処理
            page_pdfs = [pdf_bytes]

        total_pages = len(page_pdfs)
        for page_num, page_pdf in enumerate(page_pdfs, start=1):
            split_items.append((original_filename, page_pdf, page_num, total_pages))

    # 分割後のファイル総数チェック
    if len(split_items) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ページ分割後のファイル数が上限を超えています"
                f"（{len(split_items)}件 / 最大{MAX_BATCH_FILES}件）。"
                f"アップロードするPDFを減らしてください。"
            ),
        )

    # バッチジョブ作成（分割後の総ファイル数で）
    batch_id = _generate_batch_id()
    batch_store.create_job(batch_id, total_files=len(split_items))

    # バッチファイルアイテム登録
    file_data_list: list[tuple[str, bytes]] = []

    for seq, (original_filename, page_pdf, page_num, total_pages) in enumerate(
        split_items, start=1
    ):
        file_id = _generate_file_id()

        # 表示用ファイル名: 複数ページの場合は「元ファイル名_p{ページ番号}」
        if total_pages > 1:
            # 拡張子を分離してページ番号を挿入
            base_name = original_filename
            if base_name.lower().endswith(".pdf"):
                base_name = base_name[:-4]
            display_filename = f"{base_name}_p{page_num}.pdf"
        else:
            display_filename = original_filename

        # 初期バッチファイル名: 連番 + 表示ファイル名
        seq_str = str(seq).zfill(3)
        batch_filename = f"{seq_str}_{display_filename}"

        file_item = BatchFileItem(
            file_id=file_id,
            seq_number=seq,
            original_filename=display_filename,
            batch_filename=batch_filename,
            status=BatchFileStatus.QUEUED,
        )

        batch_store.add_file(batch_id, file_item)

        # ログ: 分割された場合はページ情報付き
        if total_pages > 1:
            batch_store.add_file_log(
                batch_id,
                file_id,
                f"アップロード完了: {original_filename} (ページ {page_num}/{total_pages})",
            )
        else:
            batch_store.add_file_log(
                batch_id, file_id, f"アップロード完了: {original_filename}"
            )

        file_data_list.append((file_id, page_pdf))

    # 入力PDFをZIP化してS3にアップロード（バックグラウンド）
    # 分割後の各ページPDFを保存
    pdf_files_for_s3 = [
        (
            batch_store.get_file_item(batch_id, file_id).original_filename
            if batch_store.get_file_item(batch_id, file_id)
            else f"file_{i+1}.pdf",
            pdf_bytes,
        )
        for i, (file_id, pdf_bytes) in enumerate(file_data_list)
    ]
    asyncio.create_task(_upload_input_to_s3(batch_id, pdf_files_for_s3))

    # バックグラウンドでOCR処理を開始
    asyncio.create_task(_process_batch(batch_id, file_data_list))

    # ログ出力（分割情報付き）
    uploaded_count = len(files)
    split_count = len(split_items)
    if split_count > uploaded_count:
        logger.info(
            f"[バッチ {batch_id}] アップロード完了: "
            f"{uploaded_count}件のPDF → {split_count}件に分割、"
            f"バックグラウンド処理開始"
        )
    else:
        logger.info(
            f"[バッチ {batch_id}] アップロード完了: {uploaded_count}件、バックグラウンド処理開始"
        )

    # バッチジョブ内のファイル一覧を取得（レスポンスに含める）
    job = batch_store.get_job(batch_id)

    return BatchUploadResponse(
        batch_id=batch_id,
        total_files=len(split_items),
        message=(
            f"{uploaded_count}件のPDFをアップロードしました"
            f"（{split_count}ページに分割）。バックグラウンドで処理を開始します。"
            if split_count > uploaded_count
            else f"{uploaded_count}件のファイルをアップロードしました。バックグラウンドで処理を開始します。"
        ),
        files=job.files if job else [],
    )


@router.get("/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    """バッチ処理状況を取得する"""
    job = batch_store.get_job(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="バッチジョブが見つかりません")

    return BatchStatusResponse(
        batch_id=job.batch_id,
        status=job.status,
        total_files=job.total_files,
        completed=job.completed_count,
        processing=job.processing_count,
        needs_review=job.needs_review_count,
        failed=job.failed_count,
        queued=job.queued_count,
        progress_percent=job.progress_percent,
        created_at=job.created_at,
        updated_at=job.updated_at,
        files=job.files,
    )


@router.post("/{batch_id}/files/{file_id}/reprocess")
async def reprocess_file(
    batch_id: str,
    file_id: str,
):
    """個別ファイルの再処理を実行する"""
    job = batch_store.get_job(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="バッチジョブが見つかりません")

    file_item = batch_store.get_file_item(batch_id, file_id)
    if not file_item:
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    # 再処理対象のステータス確認
    if file_item.status not in (
        BatchFileStatus.FAILED,
        BatchFileStatus.NEEDS_REVIEW,
    ):
        raise HTTPException(
            status_code=400,
            detail="再処理可能なのは「失敗」または「確認必要」のファイルのみです",
        )

    # PDFバイナリを取得
    pdf_bytes = store.get_pdf(file_id)
    if not pdf_bytes:
        raise HTTPException(
            status_code=404, detail="PDFファイルデータが見つかりません"
        )

    # ステータスをキュー待ちに戻す
    batch_store.update_file_status(batch_id, file_id, BatchFileStatus.QUEUED)
    batch_store.add_file_log(batch_id, file_id, "再処理をキューに追加")

    # ジョブステータスを処理中に
    batch_store.start_processing(batch_id)

    # バックグラウンドで再処理実行（create_taskで即時起動）
    asyncio.create_task(_process_single_file(batch_id, file_id, pdf_bytes))

    return {
        "message": "再処理を開始しました",
        "file_id": file_id,
        "batch_id": batch_id,
    }


@router.get("/{batch_id}/download/csv")
async def download_batch_csv(batch_id: str):
    """全体結果Excelダウンロード（全ファイルの結果を1つのxlsxに出力、チェック項目色分け付き）"""
    job = batch_store.get_job(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="バッチジョブが見つかりません")

    # 常に最新のインメモリデータからExcelを生成（手動ステータス変更を反映するため）
    rows = []
    for file_item in job.files:
        if file_item.status in (
            BatchFileStatus.COMPLETED,
            BatchFileStatus.NEEDS_REVIEW,
        ):
            document = store.get(file_item.file_id)
            if document:
                rows.append(_build_csv_row(document, file_item))

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="ダウンロード可能な処理結果がまだありません",
        )

    excel_bytes = _csv_generator.generate_excel(rows)
    buffer = io.BytesIO(excel_bytes)

    filename = f"OCR_BATCH_RESULT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )


@router.get("/{batch_id}/download/zip")
async def download_batch_zip(batch_id: str):
    """全原本PDFのZIPダウンロード"""
    job = batch_store.get_job(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="バッチジョブが見つかりません")

    # S3にキーが記録されている場合はPre-signed URLをJSON返却
    if job.s3_archive_key:
        filename = f"OCR_BATCH_RESULT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        presigned_url = s3_storage.generate_presigned_url(
            job.s3_archive_key, filename=filename
        )
        return {"download_url": presigned_url, "filename": filename}

    # フォールバック: S3未保存の場合はインメモリ生成
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_item in job.files:
            pdf_bytes = store.get_pdf(file_item.file_id)
            if pdf_bytes:
                zf.writestr(file_item.batch_filename, pdf_bytes)

    buffer.seek(0)

    if buffer.getbuffer().nbytes <= 22:
        raise HTTPException(
            status_code=404,
            detail="ダウンロード可能なPDFファイルがまだありません",
        )

    filename = f"OCR_BATCH_RESULT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )


def _build_csv_row(document: OcrDocument, file_item: BatchFileItem) -> dict:
    """ドキュメントからCSV行データを構築（バッチ用）"""
    field_map = {f.field_name: f for f in document.fields}

    # Excelで先頭0が消えないよう数値フィールドを保護するフィールド一覧
    NUMERIC_PRESERVE_FIELDS = {
        "口座番号", "銀行番号", "店番号", "委託者番号", "契約者番号",
        "ゆうちょ記号", "ゆうちょ番号",
    }

    def get_value(name: str) -> str:
        field = field_map.get(name)
        if field is None:
            return ""
        value = field.corrected_value or field.value or ""
        # お届出印金融機関は「あり」→OK、「なし」→NGに変換
        if name == "お届出印金融機関":
            return "OK" if value == "あり" else "NG"
        # 数値フィールドの先頭0を保持するためExcel数式形式で出力
        if value and name in NUMERIC_PRESERVE_FIELDS:
            return f'="{value}"'
        return value

    def get_check(name: str) -> str:
        field = field_map.get(name)

        # 手動チェックステータスが設定されている場合はそちらを優先
        if field and field.manual_check_status:
            status_map = {"ok": "OK", "ng": "NG", "needs_review": "要確認"}
            return status_map.get(field.manual_check_status, "OK")

        # お届出印金融機関は「あり」/「なし」で判定
        if name == "お届出印金融機関":
            if field and field.value == "あり":
                return "OK"
            return "NG"

        # 銀行系フィールドとゆうちょ系フィールドの排他判定
        bank_fields = {"銀行名", "支店名", "預金種目", "口座番号", "銀行番号", "店番号"}
        yucho_fields = {"ゆうちょ記号", "ゆうちょ番号"}

        # ゆうちょ側に値があるか判定
        has_yucho = any(
            (f := field_map.get(fn)) and f.value
            for fn in yucho_fields
        )
        # 銀行側に値があるか判定
        has_bank = any(
            (f := field_map.get(fn)) and f.value
            for fn in bank_fields
        )

        # 排他判定: 相手側に記入があり自分側が空欄の場合は正常（"-"）
        if name in bank_fields:
            if (field is None or not field.value) and has_yucho:
                return "-"
        if name in yucho_fields:
            if (field is None or not field.value) and has_bank:
                return "-"

        # 銀行名は「（x）」を含む場合NG（種別未選択）
        if name == "銀行名":
            if field is None or not field.value:
                return "NG"
            if "（x）" in field.value:
                return "NG"
            if field.confidence_level == ConfidenceLevel.LOW:
                return "要確認"
            return "OK"
        if field is None or not field.value:
            return "NG"
        if field.confidence_level == ConfidenceLevel.LOW:
            return "要確認"
        return "OK"

    processing_time = document.updated_at.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "処理日時": processing_time,
        "入力ファイル名": file_item.batch_filename,
        "預金者氏名": get_value("預金者氏名"),
        "預金者フリガナ": get_value("預金者フリガナ"),
        "銀行名": get_value("銀行名"),
        "支店名": get_value("支店名"),
        "預金種目": get_value("預金種目"),
        "口座番号": get_value("口座番号"),
        "銀行番号": get_value("銀行番号"),
        "店番号": get_value("店番号"),
        "ゆうちょ記号": get_value("ゆうちょ記号"),
        "ゆうちょ番号": get_value("ゆうちょ番号"),
        "振替日": get_value("振替日"),
        "委託者番号": get_value("委託者番号"),
        "契約者番号": get_value("契約者番号"),
        "委託者名": get_value("委託者名"),
        "料金等の種類": get_value("料金等の種類"),
        "預金者氏名_チェック": get_check("預金者氏名"),
        "預金者フリガナ_チェック": get_check("預金者フリガナ"),
        "お届出印金融機関_チェック": get_check("お届出印金融機関"),
        "銀行名_チェック": get_check("銀行名"),
        "支店名_チェック": get_check("支店名"),
        "預金種目_チェック": get_check("預金種目"),
        "口座番号_チェック": get_check("口座番号"),
        "銀行番号_チェック": get_check("銀行番号"),
        "店番号_チェック": get_check("店番号"),
        "ゆうちょ記号_チェック": get_check("ゆうちょ記号"),
        "ゆうちょ番号_チェック": get_check("ゆうちょ番号"),
        "振替日_チェック": get_check("振替日"),
        "委託者番号_チェック": get_check("委託者番号"),
        "契約者番号_チェック": get_check("契約者番号"),
        "委託者名_チェック": get_check("委託者名"),
        "料金等の種類_チェック": get_check("料金等の種類"),
    }
