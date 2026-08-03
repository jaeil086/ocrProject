"""
PDFリネームサービス

OCR処理済みPDFファイルのリネーム後ファイル名を生成し、
ダウンロード用のバイナリとファイル名をタプルで返却する。
"""

from backend.models.enums import ConfidenceLevel
from backend.models.schemas import OcrDocument


class PdfRenamer:
    """PDFファイルリネームサービス"""

    def generate_filename(self, document: OcrDocument) -> str:
        """リネーム後のPDFファイル名を生成する。"""
        return self._generate_filename(document, extension="pdf")

    def rename(
        self, original_bytes: bytes, document: OcrDocument
    ) -> tuple[bytes, str]:
        """PDFバイナリとリネーム後ファイル名を返却する。"""
        filename = self.generate_filename(document)
        return (original_bytes, filename)

    def _generate_filename(self, document: OcrDocument, extension: str) -> str:
        """
        ファイル命名規則に基づくファイル名生成

        パターン:
        1. 委託者番号または契約番号が未取得 → UNKNOWN_{FileID}.{ext}
        2. 未確認のLOW confidenceフィールドあり →★要確認_{委託者番号}_{契約番号}.{ext}
        3. 通常 → {FileID}_{委託者番号}_{契約番号}.{ext}
        """
        file_id = document.file_id
        consignor = document.consignor_number
        contract = document.contract_number

        if not consignor or not contract:
            return f"UNKNOWN_{file_id}.{extension}"

        has_unconfirmed_low = any(
            f.confidence_level == ConfidenceLevel.LOW and not f.is_confirmed
            for f in document.fields
        )

        if has_unconfirmed_low:
            return f"★要確認_{consignor}_{contract}.{extension}"

        return f"{file_id}_{consignor}_{contract}.{extension}"
