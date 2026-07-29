"""
OcrPipeline の単体テスト

OCRパイプラインオーケストレーションのロジックを検証する。
外部サービス（Textract, Bedrock）はモックで代替する。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.config import CONFIDENCE_THRESHOLD, TEXTRACT_FALLBACK_THRESHOLD
from backend.models.enums import ConfidenceLevel, DocumentStatus, FormType
from backend.models.schemas import (
    ClaudeExtractionResult,
    OcrField,
    ProcessingResult,
    TextractLine,
    TextractResult,
    TextractWord,
)
from backend.services.ocr_pipeline import OcrPipeline


@pytest.fixture
def pipeline():
    """モック化されたOcrPipelineインスタンス"""
    p = OcrPipeline()
    # 各サービスをモック化
    p.pdf_reader = MagicMock()
    p.image_preprocessor = MagicMock()
    p.textract_client = AsyncMock()
    p.claude_client = AsyncMock()
    return p


@pytest.fixture
def sample_textract_result():
    """サンプルのTextract結果"""
    return TextractResult(
        lines=[
            TextractLine(
                text="口座振替依頼書",
                confidence=95.0,
                words=[
                    TextractWord(
                        text="口座振替依頼書",
                        confidence=95.0,
                        bounding_box={"Left": 0.1, "Top": 0.1, "Width": 0.3, "Height": 0.05},
                    )
                ],
            ),
            TextractLine(
                text="東京太郎",
                confidence=85.0,
                words=[
                    TextractWord(
                        text="東京太郎",
                        confidence=85.0,
                        bounding_box={"Left": 0.1, "Top": 0.2, "Width": 0.2, "Height": 0.05},
                    )
                ],
            ),
        ],
        forms=[],
        tables=[],
    )


@pytest.fixture
def sample_claude_result():
    """サンプルのClaude抽出結果"""
    return ClaudeExtractionResult(
        form_type=FormType.GENERAL,
        extracted_fields=[
            OcrField(
                field_name="預金者名（氏名）",
                value="東京太郎",
                confidence_score=85.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="銀行名",
                value="みずほ銀行",
                confidence_score=92.0,
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
                value="A001",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="契約番号",
                value="C001",
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
    async def test_正常フロー処理(self, pipeline, sample_textract_result, sample_claude_result):
        """正常なOCRパイプライン処理が成功を返す"""
        # モック設定
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed_image"
        pipeline.textract_client.analyze_document.return_value = sample_textract_result
        pipeline.claude_client.extract_fields.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is True
        assert result.error_message is None
        assert result.document.file_id == "file-001"
        assert result.document.form_type == FormType.GENERAL
        assert len(result.document.fields) == 5

    @pytest.mark.asyncio
    async def test_PDF読み込みで空のページリスト(self, pipeline):
        """PDFからページが取得できない場合エラー結果を返す"""
        pipeline.pdf_reader.read_pages.return_value = []

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is False
        assert "ページ画像を取得できません" in result.error_message

    @pytest.mark.asyncio
    async def test_画像前処理失敗時は元画像で続行(
        self, pipeline, sample_textract_result, sample_claude_result
    ):
        """画像前処理が失敗しても元画像でOCR処理を続行する"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.side_effect = Exception("前処理エラー")
        pipeline.textract_client.analyze_document.return_value = sample_textract_result
        pipeline.claude_client.extract_fields.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        # 元画像でTextractが呼ばれる
        pipeline.textract_client.analyze_document.assert_called_once_with(b"page1_image")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_Textract_API失敗時はエラー結果(self, pipeline):
        """Textract APIが失敗した場合エラー結果を返す"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.side_effect = Exception("Textract失敗")

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is False
        assert "Textract失敗" in result.error_message

    @pytest.mark.asyncio
    async def test_Claude_API失敗時はエラー結果(
        self, pipeline, sample_textract_result
    ):
        """Claude APIが失敗した場合エラー結果を返す"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.return_value = sample_textract_result
        pipeline.claude_client.extract_fields.side_effect = Exception("Claude失敗")

        result = await pipeline.process("file-001", b"pdf_bytes")

        assert result.success is False
        assert "Claude失敗" in result.error_message

    @pytest.mark.asyncio
    async def test_ドキュメントレベルのフィールド抽出(
        self, pipeline, sample_textract_result, sample_claude_result
    ):
        """Claude結果からドキュメントレベルの主要項目が抽出される"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.return_value = sample_textract_result
        pipeline.claude_client.extract_fields.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        doc = result.document
        assert doc.depositor_name == "東京太郎"
        assert doc.bank_name == "みずほ銀行"
        assert doc.account_number == "1234567"
        assert doc.consignor_number == "A001"
        assert doc.contract_number == "C001"


class TestFallbackLogic:
    """フォールバックロジックのテスト"""

    @pytest.mark.asyncio
    async def test_Textract結果が空の場合フォールバック実行(
        self, pipeline, sample_claude_result
    ):
        """Textract認識結果が空の場合、画像付きフォールバックが実行される"""
        empty_textract = TextractResult(lines=[], forms=[], tables=[])

        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.return_value = empty_textract
        pipeline.claude_client.extract_fields_with_image.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        # extract_fields_with_imageが呼ばれている
        pipeline.claude_client.extract_fields_with_image.assert_called_once()
        # extract_fieldsは呼ばれない
        pipeline.claude_client.extract_fields.assert_not_called()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_平均Confidence低い場合フォールバック実行(
        self, pipeline, sample_claude_result
    ):
        """平均Confidence Scoreが閾値未満の場合、フォールバックが実行される"""
        low_confidence_textract = TextractResult(
            lines=[
                TextractLine(
                    text="あいまい",
                    confidence=20.0,  # TEXTRACT_FALLBACK_THRESHOLD(30.0)未満
                    words=[],
                ),
                TextractLine(
                    text="不明瞭",
                    confidence=25.0,
                    words=[],
                ),
            ],
            forms=[],
            tables=[],
        )

        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.return_value = low_confidence_textract
        pipeline.claude_client.extract_fields_with_image.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        pipeline.claude_client.extract_fields_with_image.assert_called_once()
        pipeline.claude_client.extract_fields.assert_not_called()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_平均Confidence十分な場合は通常フロー(
        self, pipeline, sample_textract_result, sample_claude_result
    ):
        """平均Confidence Scoreが閾値以上の場合、通常フローが実行される"""
        pipeline.pdf_reader.read_pages.return_value = [b"page1_image"]
        pipeline.image_preprocessor.preprocess.return_value = b"preprocessed"
        pipeline.textract_client.analyze_document.return_value = sample_textract_result
        pipeline.claude_client.extract_fields.return_value = sample_claude_result

        result = await pipeline.process("file-001", b"pdf_bytes")

        # 通常のextract_fieldsが呼ばれている
        pipeline.claude_client.extract_fields.assert_called_once()
        pipeline.claude_client.extract_fields_with_image.assert_not_called()
        assert result.success is True


class TestNeedsFallback:
    """_needs_fallbackメソッドのテスト"""

    def test_空のlines(self):
        """認識結果が空の場合True"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        result = TextractResult(lines=[], forms=[], tables=[])
        assert pipeline._needs_fallback(result) is True

    def test_平均Confidence閾値未満(self):
        """平均Confidence Scoreが閾値未満の場合True"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        result = TextractResult(
            lines=[
                TextractLine(text="a", confidence=10.0, words=[]),
                TextractLine(text="b", confidence=20.0, words=[]),
            ],
            forms=[],
            tables=[],
        )
        # 平均 = 15.0 < TEXTRACT_FALLBACK_THRESHOLD(30.0)
        assert pipeline._needs_fallback(result) is True

    def test_平均Confidence閾値以上(self):
        """平均Confidence Scoreが閾値以上の場合False"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        result = TextractResult(
            lines=[
                TextractLine(text="a", confidence=80.0, words=[]),
                TextractLine(text="b", confidence=90.0, words=[]),
            ],
            forms=[],
            tables=[],
        )
        # 平均 = 85.0 >= TEXTRACT_FALLBACK_THRESHOLD(30.0)
        assert pipeline._needs_fallback(result) is False

    def test_ちょうど閾値と同じ(self):
        """平均Confidence Scoreがちょうど閾値と同じ場合False（フォールバック不要）"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        result = TextractResult(
            lines=[
                TextractLine(text="a", confidence=TEXTRACT_FALLBACK_THRESHOLD, words=[]),
            ],
            forms=[],
            tables=[],
        )
        assert pipeline._needs_fallback(result) is False


class TestApplyConfidenceLevel:
    """_apply_confidence_levelメソッドのテスト"""

    def test_閾値以上はHIGH(self):
        """Confidence Scoreが閾値以上の場合HIGHが設定される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        field = OcrField(
            field_name="テスト",
            value="値",
            confidence_score=CONFIDENCE_THRESHOLD,
            confidence_level=ConfidenceLevel.LOW,  # 変換前
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
            confidence_level=ConfidenceLevel.HIGH,  # 変換前
        )
        result = pipeline._apply_confidence_level(field)
        assert result.confidence_level == ConfidenceLevel.LOW

    def test_フィールド値が保持される(self):
        """ConfidenceLevel変換後も他のフィールド値が保持される"""
        pipeline = OcrPipeline.__new__(OcrPipeline)
        field = OcrField(
            field_name="銀行名",
            value="みずほ銀行",
            confidence_score=95.0,
            confidence_level=ConfidenceLevel.LOW,
            is_confirmed=True,
            corrected_value="三井住友銀行",
        )
        result = pipeline._apply_confidence_level(field)
        assert result.field_name == "銀行名"
        assert result.value == "みずほ銀行"
        assert result.confidence_score == 95.0
        assert result.is_confirmed is True
        assert result.corrected_value == "三井住友銀行"


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
