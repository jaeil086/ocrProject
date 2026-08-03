"""
PDFリネームサービスのテスト

テスト対象: backend/services/pdf_renamer.py
対象要件: Requirements 9.1, 9.2, 9.3, 9.4
"""

import pytest

from backend.models.enums import ConfidenceLevel, DocumentStatus
from backend.models.schemas import OcrDocument, OcrField
from backend.services.pdf_renamer import PdfRenamer


@pytest.fixture
def renamer() -> PdfRenamer:
    """PdfRenamerインスタンスを返却するフィクスチャ"""
    return PdfRenamer()


def _make_document(
    file_id: str = "FILE001",
    consignor_number: str | None = "12345",
    contract_number: str | None = "67890",
    fields: list[OcrField] | None = None,
) -> OcrDocument:
    """テスト用OcrDocumentを生成するヘルパー"""
    if fields is None:
        fields = []
    return OcrDocument(
        file_id=file_id,
        original_filename="test.pdf",
        status=DocumentStatus.NORMAL,
        consignor_number=consignor_number,
        contract_number=contract_number,
        fields=fields,
    )


class TestGenerateFilename:
    """generate_filename() のテスト"""

    def test_normal_format(self, renamer: PdfRenamer):
        """通常のファイル名フォーマット: {FileID}_{委託者番号}_{契約番号}.pdf"""
        document = _make_document(
            file_id="FILE001",
            consignor_number="12345",
            contract_number="67890",
            fields=[
                OcrField(
                    field_name="預金者名",
                    value="テスト太郎",
                    confidence_score=90.0,
                    confidence_level=ConfidenceLevel.HIGH,
                )
            ],
        )
        result = renamer.generate_filename(document)
        assert result == "FILE001_12345_67890.pdf"

    def test_with_review_marker(self, renamer: PdfRenamer):
        """未確認LOW項目あり: {★要確認_{委託者番号}_{契約番号}.pdf"""
        document = _make_document(
            file_id="FILE002",
            consignor_number="11111",
            contract_number="22222",
            fields=[
                OcrField(
                    field_name="預金者名",
                    value="テスト太郎",
                    confidence_score=50.0,
                    confidence_level=ConfidenceLevel.LOW,
                    is_confirmed=False,
                )
            ],
        )
        result = renamer.generate_filename(document)
        assert result == "★要確認_11111_22222.pdf"

    def test_confirmed_low_field_no_review_marker(self, renamer: PdfRenamer):
        """確認済みLOW項目のみ: ★要確認マーカーなし"""
        document = _make_document(
            file_id="FILE003",
            consignor_number="33333",
            contract_number="44444",
            fields=[
                OcrField(
                    field_name="預金者名",
                    value="テスト太郎",
                    confidence_score=50.0,
                    confidence_level=ConfidenceLevel.LOW,
                    is_confirmed=True,
                )
            ],
        )
        result = renamer.generate_filename(document)
        assert result == "FILE003_33333_44444.pdf"

    def test_missing_consignor_number(self, renamer: PdfRenamer):
        """委託者番号が未取得: UNKNOWN_{FileID}.pdf"""
        document = _make_document(
            file_id="FILE004",
            consignor_number=None,
            contract_number="55555",
        )
        result = renamer.generate_filename(document)
        assert result == "UNKNOWN_FILE004.pdf"

    def test_missing_contract_number(self, renamer: PdfRenamer):
        """契約番号が未取得: UNKNOWN_{FileID}.pdf"""
        document = _make_document(
            file_id="FILE005",
            consignor_number="66666",
            contract_number=None,
        )
        result = renamer.generate_filename(document)
        assert result == "UNKNOWN_FILE005.pdf"

    def test_both_numbers_missing(self, renamer: PdfRenamer):
        """委託者番号・契約番号が両方とも未取得: UNKNOWN_{FileID}.pdf"""
        document = _make_document(
            file_id="FILE006",
            consignor_number=None,
            contract_number=None,
        )
        result = renamer.generate_filename(document)
        assert result == "UNKNOWN_FILE006.pdf"

    def test_empty_consignor_number(self, renamer: PdfRenamer):
        """委託者番号が空文字: UNKNOWN_{FileID}.pdf"""
        document = _make_document(
            file_id="FILE007",
            consignor_number="",
            contract_number="77777",
        )
        result = renamer.generate_filename(document)
        assert result == "UNKNOWN_FILE007.pdf"

    def test_empty_contract_number(self, renamer: PdfRenamer):
        """契約番号が空文字: UNKNOWN_{FileID}.pdf"""
        document = _make_document(
            file_id="FILE008",
            consignor_number="88888",
            contract_number="",
        )
        result = renamer.generate_filename(document)
        assert result == "UNKNOWN_FILE008.pdf"


class TestRename:
    """rename() のテスト"""

    def test_returns_same_bytes_with_new_filename(self, renamer: PdfRenamer):
        """rename()は元のバイナリをそのまま返し、新しいファイル名を付与する"""
        original_bytes = b"%PDF-1.4 fake pdf content here"
        document = _make_document(
            file_id="FILE010",
            consignor_number="99999",
            contract_number="00001",
            fields=[
                OcrField(
                    field_name="銀行名",
                    value="テスト銀行",
                    confidence_score=85.0,
                    confidence_level=ConfidenceLevel.HIGH,
                )
            ],
        )

        result_bytes, result_filename = renamer.rename(original_bytes, document)

        # バイナリが変更されていないことを確認
        assert result_bytes is original_bytes
        assert result_bytes == b"%PDF-1.4 fake pdf content here"
        # ファイル名が正しく生成されていることを確認
        assert result_filename == "FILE010_99999_00001.pdf"

    def test_rename_with_review_items(self, renamer: PdfRenamer):
        """要確認項目がある場合のrename()テスト"""
        original_bytes = b"pdf binary data"
        document = _make_document(
            file_id="FILE011",
            consignor_number="11111",
            contract_number="22222",
            fields=[
                OcrField(
                    field_name="口座番号",
                    value="1234567",
                    confidence_score=40.0,
                    confidence_level=ConfidenceLevel.LOW,
                    is_confirmed=False,
                )
            ],
        )

        result_bytes, result_filename = renamer.rename(original_bytes, document)

        assert result_bytes is original_bytes
        assert result_filename == "★要確認_11111_22222.pdf"

    def test_rename_with_unknown_format(self, renamer: PdfRenamer):
        """番号未取得の場合のrename()テスト"""
        original_bytes = b"another pdf"
        document = _make_document(
            file_id="FILE012",
            consignor_number=None,
            contract_number=None,
        )

        result_bytes, result_filename = renamer.rename(original_bytes, document)

        assert result_bytes is original_bytes
        assert result_filename == "UNKNOWN_FILE012.pdf"

    def test_rename_preserves_large_binary(self, renamer: PdfRenamer):
        """大きなバイナリデータも変更されないことを確認"""
        original_bytes = b"\x00" * 10000  # 10KB
        document = _make_document(file_id="FILE013")

        result_bytes, result_filename = renamer.rename(original_bytes, document)

        assert result_bytes is original_bytes
        assert len(result_bytes) == 10000
