"""
POST /api/upload の統合テスト

正常系:
- 有効なPDFファイルのアップロード（OCRパイプラインをモック）
- 複数ファイルの同時アップロード

異常系:
- PDF形式でないファイルのアップロード → 400エラー
"""

import io
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.enums import ConfidenceLevel, DocumentStatus, FormType
from backend.models.schemas import (
    ClaudeExtractionResult,
    OcrDocument,
    OcrField,
    ProcessingResult,
)


def _make_mock_processing_result(file_id: str) -> ProcessingResult:
    """テスト用のProcessingResultを生成する"""
    fields = [
        OcrField(
            field_name="預金者名（フリガナ）",
            value="タナカ タロウ",
            confidence_score=95.0,
            confidence_level=ConfidenceLevel.HIGH,
        ),
        OcrField(
            field_name="預金者名（氏名）",
            value="田中 太郎",
            confidence_score=90.0,
            confidence_level=ConfidenceLevel.HIGH,
        ),
        OcrField(
            field_name="銀行名",
            value="テスト銀行",
            confidence_score=85.0,
            confidence_level=ConfidenceLevel.HIGH,
        ),
        OcrField(
            field_name="支店名",
            value="テスト支店",
            confidence_score=80.0,
            confidence_level=ConfidenceLevel.HIGH,
        ),
        OcrField(
            field_name="口座番号",
            value="1234567",
            confidence_score=92.0,
            confidence_level=ConfidenceLevel.HIGH,
        ),
    ]

    document = OcrDocument(
        file_id=file_id,
        original_filename="",
        form_type=FormType.GENERAL,
        status=DocumentStatus.PROCESSING,
        fields=fields,
        validation_errors=[],
        visual_checks=[],
        consignor_number="11111",
        contract_number="22222",
    )

    return ProcessingResult(document=document, success=True, error_message=None)


@pytest.mark.asyncio
async def test_upload_valid_pdf(client):
    """正常系: 有効なPDFファイルのアップロードが成功する"""
    # OCRパイプラインをモックして外部サービス呼び出しを回避
    with patch(
        "backend.routers.upload._ocr_pipeline.process",
        new_callable=AsyncMock,
    ) as mock_process:
        # file_idは内部で採番されるので、side_effectでprocessに渡されたfile_idを使用
        async def mock_process_fn(file_id, pdf_bytes):
            return _make_mock_processing_result(file_id)

        mock_process.side_effect = mock_process_fn

        # PDFファイルのモック（バイナリデータ）
        pdf_content = b"%PDF-1.4 fake pdf content"
        files = {"files": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}

        response = await client.post("/api/upload", files=[("files", ("test.pdf", io.BytesIO(pdf_content), "application/pdf"))])

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["files"]) == 1

        file_result = data["files"][0]
        assert file_result["file_id"] is not None
        assert file_result["original_filename"] == "test.pdf"
        assert file_result["status"] in ["normal", "needs_review", "deficient"]
        assert isinstance(file_result["fields"], list)


@pytest.mark.asyncio
async def test_upload_non_pdf_file_returns_400(client):
    """異常系: PDF形式でないファイルは400エラーを返す"""
    # テキストファイルをアップロード
    text_content = b"This is not a PDF file"

    response = await client.post(
        "/api/upload",
        files=[("files", ("test.txt", io.BytesIO(text_content), "text/plain"))],
    )

    assert response.status_code == 400
    data = response.json()
    assert "PDF形式のファイルを選択してください" in data["detail"]


@pytest.mark.asyncio
async def test_upload_multiple_pdf_files(client):
    """正常系: 複数PDFファイルの同時アップロードが成功する"""
    with patch(
        "backend.routers.upload._ocr_pipeline.process",
        new_callable=AsyncMock,
    ) as mock_process:
        async def mock_process_fn(file_id, pdf_bytes):
            return _make_mock_processing_result(file_id)

        mock_process.side_effect = mock_process_fn

        pdf_content_1 = b"%PDF-1.4 fake pdf 1"
        pdf_content_2 = b"%PDF-1.4 fake pdf 2"

        response = await client.post(
            "/api/upload",
            files=[
                ("files", ("doc1.pdf", io.BytesIO(pdf_content_1), "application/pdf")),
                ("files", ("doc2.pdf", io.BytesIO(pdf_content_2), "application/pdf")),
            ],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["files"]) == 2

        # 各ファイルが異なるfile_idを持つことを確認
        file_ids = [f["file_id"] for f in data["files"]]
        assert len(set(file_ids)) == 2

        # ファイル名がそれぞれ正しいことを確認
        filenames = [f["original_filename"] for f in data["files"]]
        assert "doc1.pdf" in filenames
        assert "doc2.pdf" in filenames


@pytest.mark.asyncio
async def test_upload_mixed_files_returns_400(client):
    """異常系: PDFと非PDFファイルの混在は400エラーを返す"""
    pdf_content = b"%PDF-1.4 fake pdf"
    text_content = b"Not a PDF"

    response = await client.post(
        "/api/upload",
        files=[
            ("files", ("doc.pdf", io.BytesIO(pdf_content), "application/pdf")),
            ("files", ("readme.txt", io.BytesIO(text_content), "text/plain")),
        ],
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_ocr_pipeline_failure(client):
    """異常系: OCRパイプラインが失敗した場合でも処理結果を返す"""
    with patch(
        "backend.routers.upload._ocr_pipeline.process",
        new_callable=AsyncMock,
    ) as mock_process:
        # OCR失敗を模擬
        async def mock_process_fn(file_id, pdf_bytes):
            document = OcrDocument(
                file_id=file_id,
                original_filename="",
                form_type=None,
                status=DocumentStatus.PROCESSING,
                fields=[],
                validation_errors=[],
                visual_checks=[],
            )
            return ProcessingResult(
                document=document,
                success=False,
                error_message="Textract API呼び出しに失敗しました",
            )

        mock_process.side_effect = mock_process_fn

        pdf_content = b"%PDF-1.4 fake pdf"
        response = await client.post(
            "/api/upload",
            files=[("files", ("test.pdf", io.BytesIO(pdf_content), "application/pdf"))],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        file_result = data["files"][0]
        assert file_result["status"] == "processing"
        assert len(file_result["errors"]) > 0
