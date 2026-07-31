"""
OcrPipeline の単体テスト

OCRパイプラインオーケストレーションのロジックを検証する。
外部サービス（Bedrock Claude）はモックで代替する。
Claude Sonnet単独構成（Textract不使用）に対応。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.config import CONFIDENCE_THRESHOLD
from backend.models.enums import ConfidenceLevel, DocumentStatus, FormType
from backend.models.schemas import (
    ClaudeExtractionResult,
    OcrField,
    ProcessingResult,
)
from backend.services.ocr_pipeline import OcrPipeline


@pytest.fixture
def pipeline():
    """モック化されたOcrPipelineインスタンス"""
    p = OcrPipeline()
    # 各サービスをモック化
    p.pdf_reader = MagicMock()
    p.image_preprocessor = MagicMock()
    p.claude_client = AsyncMock()
    return p


@pytest.fixture
def sample_claude_result():
    """サンプルのClaude抽出結果（2段階OCR方式）"""
    return ClaudeExtractionResult(
        form_type=FormType.GENERAL,
        extracted_fields=[
            OcrField(
                field_name="預金者名氏名",
                value="東京太郎",
                confidence_score=85.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="口座番号",
                value="1234567",
                confidence_score=60.0,
                confidence_level=ConfidenceLevel.LOW,
            ),
            OcrField(
                field_name="委託者番号",
                value="11137",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="契約者番号",
                value="10116",
                confidence_score=88.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="銀行番号",
                value="0009",
                confidence_score=92.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="支店番号",
                value="681",
                confidence_score=88.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ],
        needs_review_fields=["口座番号"],
        deficiency_notes=[],
        correction_suggestions={},
    )


class TestOcrPipelineProcess:
    """OcrPipeline.process()のテスト"""

    @pytest.mark.asyncio
    async def test_正常フロー処理(self, pipeline, sample_claude_result):
        """正常なOCRパイプライン処理が成功を返す"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed_image"
        pipeline.claude_client.extract_fields_from_image.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is True
        assert result.error_message is None
        assert result.document.file_id == "file-001"
        assert result.document.form_type == FormType.GENERAL
        assert len(result.document.fields) == 6

    @pytest.mark.asyncio
    async def test_PDF読み込みで空のページリスト(self, pipeline):
        """PDFからページが取得できない場合エラー結果を返す"""
        pipeline.pdf_reader.read_pages.return_value = []

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is False
        assert "ページ画像を取得できません" in result.error_message

    @pytest.mark.asyncio
    async def test_Claude_API失敗時はエラー結果(self, pipeline):
        """Claude APIが失敗した場合エラー結果を返す"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.claude_client.extract_fields_from_image.side_effect = Exception("Claude失敗")

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is False
        assert "Claude失敗" in result.error_message

    @pytest.mark.asyncio
    async def test_ドキュメントレベルのフィールド抽出(self, pipeline, sample_claude_result):
        """Claude結果からドキュメントレベルの主要項目が抽出される"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.claude_client.extract_fields_from_image.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        doc = result.document
        assert doc.depositor_name == "東京太郎"
        assert doc.account_number == "1234567"
        assert doc.consignor_number == "11137"
        assert doc.contract_number == "10116"
        assert doc.bank_code == "0009"
        assert doc.branch_code == "681"

    @pytest.mark.asyncio
    async def test_前処理画像がClaudeに渡される(self, pipeline, sample_claude_result):
        """前処理後の画像がClaude OCRに渡される"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed_image"
        pipeline.claude_client.extract_fields_from_image.return_value = sample_claude_result

        await pipeline.process("file-001", b"pdf_bytes")

        pipeline.claude_client.extract_fields_from_image.assert_called_once_with(
            b"preprocessed_image"
        )

    @pytest.mark.asyncio
    async def test_最初のページのみ処理(self, pipeline, sample_claude_result):
        """複数ページPDFでもMVPとして最初のページのみ処理する"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1", b"page2", b"page3"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.claude_client.extract_fields_from_image.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        # 前処理は最初のページのみ
        pipeline.image_preprocessor.preprocess.assert_called_once_with(b"page1")
        assert result.success is True


class TestApplyConfidenceLevel:
    """_apply_confidence_levelメソッドのテスト"""

    def test_閾値以上はHIGH(self):
        """Confidence Scoreが閾値以上の場合HIGHが設定される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        field = OcrField(
            field_name="テスト",
            value="値",
            confidence_score=CONFIDENCE_THRESHOLD,
            confidence_level=ConfidenceLevel.LOW,
        )
        result = pipeline._apply_confidence_level(field)
        assert result.confidence_level == ConfidenceLevel.HIGH

    def test_閾値未満はLOW(self):
        """Confidence Scoreが閾値未満の場合LOWが設定される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        field = OcrField(
            field_name="テスト",
            value="値",
            confidence_score=CONFIDENCE_THRESHOLD - 0.1,
            confidence_level=ConfidenceLevel.HIGH,
        )
        result = pipeline._apply_confidence_level(field)
        assert result.confidence_level == ConfidenceLevel.LOW

    def test_フィールド値が保持される(self):
        """ConfidenceLevel変換後も他のフィールド値が保持される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        field = OcrField(
            field_name="銀行番号",
            value="0009",
            confidence_score=95.0,
            confidence_level=ConfidenceLevel.LOW,
            is_confirmed=True,
            corrected_value="0019",
        )
        result = pipeline._apply_confidence_level(field)
        assert result.field_name == "銀行番号"
        assert result.value == "0009"
        assert result.confidence_score == 95.0
        assert result.is_confirmed is True
        assert result.corrected_value == "0019"


class TestCreateErrorResult:
    """_create_error_resultメソッドのテスト"""

    def test_エラー結果の構造(self):
        """エラー結果が正しい構造で返される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        result = pipeline._create_error_result("file-001", "テストエラー")

        assert result.success is False
        assert result.error_message == "テストエラー"
        assert result.document.file_id == "file-001"
        assert result.document.status == DocumentStatus.PROCESSING
        assert result.document.fields == []
        assert result.document.form_type is None


class TestBuildDocument:
    """_build_documentメソッドのテスト"""

    def test_フィールドマッピングが正しい(self, sample_claude_result):
        """Claude結果のフィールドがOcrDocumentに正しくマッピングされる"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        doc = pipeline._build_document("file-001", sample_claude_result)

        assert doc.file_id == "file-001"
        assert doc.form_type == FormType.GENERAL
        assert doc.status == DocumentStatus.PROCESSING
        assert doc.consignor_number == "11137"
        assert doc.contract_number == "10116"
        assert doc.bank_code == "0009"
        assert doc.branch_code == "681"
        assert doc.account_number == "1234567"
        assert doc.depositor_name == "東京太郎"

    def test_存在しないフィールドはNone(self):
        """Claude結果に含まれないフィールドはNoneになる"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        minimal_result = ClaudeExtractionResult(
            form_type=FormType.GENERAL,
            extracted_fields=[
                OcrField(
                    field_name="収納代行会社名",
                    value="きらぼしシステム株式会社",
                    confidence_score=90.0,
                    confidence_level=ConfidenceLevel.HIGH,
                ),
            ],
            needs_review_fields=[],
            deficiency_notes=[],
            correction_suggestions={},
        )
        doc = pipeline._build_document("file-002", minimal_result)

        assert doc.consignor_number is None
        assert doc.contract_number is None
        assert doc.bank_code is None
        assert doc.branch_code is None
        assert doc.account_number is None
        assert doc.depositor_name is None
