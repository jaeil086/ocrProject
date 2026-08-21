"""
OCRパイプラインオーケストレーション

PDF読み込み→画像前処理→Claude Sonnet 4（画像直接OCR）→ProcessingResult
の一連のパイプラインを管理する。

パフォーマンス最適化:
  - 各処理段階の所要時間を計測ログとして出力
  - CPU集約的処理はasyncio.to_threadでスレッドプール実行
  - Claude API呼び出しは1回のみ（1段階統合方式）
"""

import asyncio
import logging
import time
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
from backend.services.validator import Validator

logger = logging.getLogger(__name__)


class OcrPipeline:
    """OCRパイプライン — Claude Sonnet 4単独構成"""

    def __init__(self):
        self.pdf_reader = PdfReader()
        self.image_preprocessor = ImagePreprocessor()
        self.claude_client = ClaudeClient()
        self.validator = Validator()

    async def process(
        self,
        file_id: str,
        pdf_bytes: bytes,
        progress_callback=None,
    ) -> ProcessingResult:
        """
        OCRパイプラインのメイン処理

        処理フロー:
        1. PyMuPDF: PDF→ページ画像変換 (10%→25%)
        2. 画像前処理（サイズ圧縮） (25%→35%)
        3. Claude Sonnet 4: 画像から直接OCR+フィールド抽出 (35%→80%)
        4. ProcessingResult構築 (80%→85%)

        Args:
            progress_callback: 進捗更新コールバック(progress: int) -> None
        """
        def _update_progress(p: int):
            if progress_callback:
                progress_callback(p)

        pipeline_start = time.perf_counter()

        try:
            # Step 1: PDF読み込み（CPU集約的なためスレッドプールで実行）
            logger.info(f"[{file_id}] PDF読み込み開始 (入力サイズ: {len(pdf_bytes)/1024:.0f}KB)")
            _update_progress(15)

            t0 = time.perf_counter()
            page_images = await asyncio.to_thread(
                self.pdf_reader.read_pages, pdf_bytes
            )
            t_pdf = time.perf_counter() - t0
            logger.info(
                f"[{file_id}] PDF読み込み完了: {t_pdf:.2f}秒, "
                f"ページ数={len(page_images)}, "
                f"1ページ目サイズ={len(page_images[0])/1024:.0f}KB"
                if page_images else f"[{file_id}] PDF読み込み完了: {t_pdf:.2f}秒, ページなし"
            )
            _update_progress(25)

            if not page_images:
                return self._create_error_result(
                    file_id, "PDFからページ画像を取得できませんでした"
                )

            # MVP: 最初のページのみ処理
            first_page_image = page_images[0]

            # Step 2: 画像前処理（CPU集約的なためスレッドプールで実行）
            logger.info(f"[{file_id}] 画像前処理開始 (入力サイズ: {len(first_page_image)/1024:.0f}KB)")
            _update_progress(30)

            t1 = time.perf_counter()
            preprocessed_image = await asyncio.to_thread(
                self.image_preprocessor.preprocess, first_page_image
            )
            t_preprocess = time.perf_counter() - t1
            logger.info(
                f"[{file_id}] 画像前処理完了: {t_preprocess:.2f}秒, "
                f"出力サイズ={len(preprocessed_image)/1024:.0f}KB"
            )
            _update_progress(35)

            # Step 3: Claude Sonnet 4で画像から直接OCR+抽出（1回のAPI呼び出し）
            logger.info(f"[{file_id}] Claude Sonnet 4 OCR開始 (画像サイズ: {len(preprocessed_image)/1024:.0f}KB)")
            _update_progress(40)

            t2 = time.perf_counter()
            claude_result = await self.claude_client.extract_fields_from_image(
                preprocessed_image
            )
            t_claude = time.perf_counter() - t2
            logger.info(
                f"[{file_id}] Claude OCR完了: {t_claude:.2f}秒, "
                f"抽出フィールド数={len(claude_result.extracted_fields)}"
            )
            _update_progress(80)

            # Step 4: ProcessingResult構築
            logger.info(f"[{file_id}] 処理結果構築")
            document = self._build_document(file_id, claude_result)
            _update_progress(85)

            # Step 5: 銀行番号/店番号の桁数チェック・入れ替わり修正
            self.validator.fix_swapped_bank_branch_codes(document.fields)
            # ゆうちょ記号/番号の桁数チェック・区切り修正
            self.validator.fix_yucho_codes(document.fields)

            # Step 6: 金融機関マスター検証
            logger.info(f"[{file_id}] 金融機関マスター検証開始")
            t3 = time.perf_counter()
            try:
                master_errors = await self.validator.check_financial_codes(
                    document.fields
                )
                document.validation_errors.extend(master_errors)
            except Exception as e:
                logger.warning(
                    f"[{file_id}] 金融機関マスター検証でエラー（処理継続）: {e}"
                )
            t_master = time.perf_counter() - t3
            logger.info(f"[{file_id}] 金融機関マスター検証完了: {t_master:.2f}秒")
            _update_progress(90)

            # パイプライン全体の計測ログ
            total_time = time.perf_counter() - pipeline_start
            logger.info(
                f"[{file_id}] パイプライン完了: 合計{total_time:.2f}秒 "
                f"(PDF:{t_pdf:.2f}s + 前処理:{t_preprocess:.2f}s + "
                f"Claude:{t_claude:.2f}s + マスター検証:{t_master:.2f}s)"
            )

            return ProcessingResult(
                document=document,
                success=True,
                error_message=None,
            )

        except Exception as e:
            total_time = time.perf_counter() - pipeline_start
            logger.error(
                f"[{file_id}] OCRパイプライン処理中にエラー ({total_time:.2f}秒経過): "
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
            bank_name=field_map.get("銀行名"),
            branch_name=field_map.get("支店名"),
            bank_code=field_map.get("銀行番号"),
            branch_code=field_map.get("店番号"),
            account_number=field_map.get("口座番号"),
            depositor_name=field_map.get("預金者氏名"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def _apply_confidence_level(self, field: OcrField) -> OcrField:
        """ConfidenceLevel判定
        値がnull（空欄）のフィールドはconfidence判定不要（空欄は正常なのでHIGH扱い）
        """
        if not field.value:
            confidence_level = ConfidenceLevel.HIGH
        else:
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
