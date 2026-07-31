"""
OCRパイプラインオーケストレーション

PDF読み込み→画像前処理→Claude Sonnet 4（画像直接OCR）→ProcessingResult
の一連のパイプラインを管理する。
Textractは使用しない（MVP構成）。
"""

import logging
import traceback
from datetime import datetime

from backend.config import CONFIDENCE_THRESHOLD
from backend.models.enums import ConfidenceLevel, DocumentStatus
from backend.models.schemas import (
    ClaudeExtractionResult,
    OcrDocument,
    OcrField,
    ProcessingResult,
)
from backend.services.claude_client import ClaudeClient
from backend.services.image_preprocessor import ImagePreprocessor
from backend.services.pdf_reader import PdfReader

logger = logging.getLogger(__name__)


class OcrPipeline:
    """OCRパイプライン — Claude Sonnet 4単独構成"""

    def __init__(self):
        self.pdf_reader = PdfReader()
        self.image_preprocessor = ImagePreprocessor()
        self.claude_client = ClaudeClient()

    async def process(self, file_id: str, pdf_bytes: bytes) -> ProcessingResult:
        """
        OCRパイプラインのメイン処理

        処理フロー:
        1. PyMuPDF: PDF→ページ画像変換
        2. 画像前処理（パススルー）
        3. Claude Sonnet 4: 画像から直接OCR+フィールド抽出
        4. ProcessingResult構築
        """
        try:
            # Step 1: PDF読み込み
            logger.info(f"[{file_id}] PDF読み込み開始")
            page_images = self.pdf_reader.read_pages(pdf_bytes)

            if not page_images:
                return self._create_error_result(
                    file_id, "PDFからページ画像を取得できませんでした"
                )

            # MVP: 最初のページのみ処理
            first_page_image = page_images[0]

            # Step 2: 画像前処理（パススルー）
            logger.info(f"[{file_id}] 画像前処理開始")
            preprocessed_image = self.image_preprocessor.preprocess(first_page_image)

            # Step 3: Claude Sonnet 4で画像から直接OCR+抽出
            logger.info(f"[{file_id}] Claude Sonnet 4 OCR開始")
            claude_result = await self.claude_client.extract_fields_from_image(
                preprocessed_image
            )

            # Step 4: ProcessingResult構築
            logger.info(f"[{file_id}] 処理結果構築")
            document = self._build_document(file_id, claude_result)

            return ProcessingResult(
                document=document,
                success=True,
                error_message=None,
            )

        except Exception as e:
            logger.error(
                f"[{file_id}] OCRパイプライン処理中にエラー: "
                f"{type(e).__name__}: {e}"
            )
            logger.error(
                f"[{file_id}] スタックトレース:\n{traceback.format_exc()}"
            )
            if hasattr(e, "response"):
                logger.error(f"[{file_id}] AWSレスポンス: {e.response}")
            return self._create_error_result(file_id, str(e))

    def _build_document(
        self, file_id: str, claude_result: ClaudeExtractionResult
    ) -> OcrDocument:
        """Claude抽出結果からOcrDocumentを構築"""
        fields = [
            self._apply_confidence_level(field)
            for field in claude_result.extracted_fields
        ]

        field_map = {f.field_name: f.value for f in fields}
        status = DocumentStatus.PROCESSING

        return OcrDocument(
            file_id=file_id,
            original_filename="",
            form_type=claude_result.form_type,
            status=status,
            fields=fields,
            validation_errors=[],
            visual_checks=[],
            consignor_number=field_map.get("委託者番号"),
            contract_number=field_map.get("契約者番号"),
            bank_name=None,
            branch_name=None,
            bank_code=field_map.get("銀行番号"),
            branch_code=field_map.get("支店番号"),
            account_number=field_map.get("口座番号"),
            depositor_name=field_map.get("預金者名氏名"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def _apply_confidence_level(self, field: OcrField) -> OcrField:
        """ConfidenceLevel判定"""
        confidence_level = (
            ConfidenceLevel.HIGH
            if field.confidence_score >= CONFIDENCE_THRESHOLD
            else ConfidenceLevel.LOW
        )

        return OcrField(
            field_name=field.field_name,
            value=field.value,
            confidence_score=field.confidence_score,
            confidence_level=confidence_level,
            is_confirmed=field.is_confirmed,
            corrected_value=field.corrected_value,
        )

    def _create_error_result(
        self, file_id: str, error_message: str
    ) -> ProcessingResult:
        """エラー時のProcessingResult生成"""
        document = OcrDocument(
            file_id=file_id,
            original_filename="",
            form_type=None,
            status=DocumentStatus.PROCESSING,
            fields=[],
            validation_errors=[],
            visual_checks=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        return ProcessingResult(
            document=document,
            success=False,
            error_message=error_message,
        )
