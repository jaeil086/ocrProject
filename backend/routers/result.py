"""
結果操作ルーター

OCR処理結果の取得・修正・確認・ダウンロードを行うAPIエンドポイント群。
"""

import io
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.models.schemas import (
    ConfirmRequest,
    FieldUpdateRequest,
    OcrDocument,
    OcrField,
    VisualCheck,
    VisualCheckUpdateRequest,
)
from backend.services.csv_generator import CsvGenerator
from backend.services.pdf_renamer import PdfRenamer
from backend.services.store import store

router = APIRouter(prefix="/api")

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
    """フィールド修正"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    for field in document.fields:
        if field.field_name == request.field_name:
            field.corrected_value = request.corrected_value
            field.is_confirmed = True
            document.updated_at = datetime.now()
            store.update(document)
            return field

    raise HTTPException(
        status_code=404,
        detail=f"フィールド '{request.field_name}' が見つかりません",
    )


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
async def download_csv(file_id: str):
    """CSV生成・ダウンロード"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

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
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

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
async def download_pdf(file_id: str):
    """リネーム済みPDFダウンロード"""
    document = store.get(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="結果が見つかりません")

    pdf_bytes = store.get_pdf(file_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDFファイルが見つかりません")

    _, filename = _pdf_renamer.rename(pdf_bytes, document)
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )
