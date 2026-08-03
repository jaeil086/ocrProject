"""
CSV生成サービスのテスト

CsvGenerator.generate() と CsvGenerator.generate_filename() の動作を検証する。
check-results.csv形式（UTF-8 BOM）に対応。
"""

import io

import pandas as pd
import pytest

from backend.models.enums import (
    ConfidenceLevel,
    DocumentStatus,
    FormType,
)
from backend.models.schemas import OcrDocument, OcrField
from backend.services.csv_generator import CsvGenerator, CSV_COLUMNS, _generate_filename


@pytest.fixture
def csv_generator():
    """CsvGeneratorインスタンスを生成"""
    return CsvGenerator()


@pytest.fixture
def sample_document():
    """テスト用OcrDocumentを生成（新check-results形式）"""
    return OcrDocument(
        file_id="FILE001",
        original_filename="test.pdf",
        form_type=FormType.GENERAL,
        status=DocumentStatus.NORMAL,
        consignor_number="12345",
        contract_number="67890",
        fields=[
            OcrField(
                field_name="預金者氏名",
                value="山田太郎",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="預金者フリガナ",
                value="ヤマダ タロウ",
                confidence_score=95.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="銀行名",
                value="みずほ銀行",
                confidence_score=88.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="支店名",
                value="東京中央支店",
                confidence_score=85.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="預金種目",
                value="普通",
                confidence_score=95.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="口座番号",
                value="1234567",
                confidence_score=92.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="銀行番号",
                value="0001",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="店番号",
                value="001",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="振替日",
                value="27",
                confidence_score=92.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="委託者番号",
                value="12345",
                confidence_score=95.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="契約者番号",
                value="67890",
                confidence_score=88.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="委託者名",
                value="テスト株式会社",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="料金等の種類",
                value="ご利用料",
                confidence_score=92.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ],
        validation_errors=[],
    )


class TestCsvGeneratorGenerate:
    """CsvGenerator.generate() のテスト"""

    def test_generate_produces_valid_utf8_bom_csv(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()がUTF-8 BOM付きの有効なCSVを生成する"""
        csv_bytes = csv_generator.generate(sample_document)

        # UTF-8 BOMが先頭にあること
        assert csv_bytes[:3] == b'\xef\xbb\xbf'

        # UTF-8でデコード可能であること
        csv_text = csv_bytes.decode("utf-8-sig")
        assert len(csv_text) > 0

        # CSVとしてパース可能であること
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
        assert len(df) == 1

    def test_generate_includes_processing_time_and_filename(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が処理日時と入力ファイル名を含む"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        assert "処理日時" in df.columns
        assert "入力ファイル名" in df.columns
        assert df.iloc[0]["入力ファイル名"] == "test.pdf"

    def test_generate_includes_japanese_field_values(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が日本語フィールド値を正しくCSVに含める"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        assert df.iloc[0]["預金者氏名"] == "山田太郎"
        assert df.iloc[0]["預金者フリガナ"] == "ヤマダ タロウ"
        assert df.iloc[0]["銀行名"] == "みずほ銀行"
        assert df.iloc[0]["支店名"] == "東京中央支店"
        assert df.iloc[0]["委託者名"] == "テスト株式会社"

    def test_generate_includes_check_columns(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が各フィールドのチェック結果カラムを含む"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        # 全チェックカラムが存在すること
        check_columns = [c for c in df.columns if c.endswith("_チェック")]
        assert len(check_columns) == 13

        # HIGHのフィールドは全て"OK"
        assert df.iloc[0]["預金者氏名_チェック"] == "OK"
        assert df.iloc[0]["口座番号_チェック"] == "OK"

    def test_generate_check_columns_ng_for_missing_value(
        self, csv_generator: CsvGenerator
    ):
        """値がないフィールドのチェック結果がNGになること"""
        doc = OcrDocument(
            file_id="FILE002",
            original_filename="test2.pdf",
            form_type=FormType.GENERAL,
            status=DocumentStatus.PROCESSING,
            fields=[
                OcrField(
                    field_name="預金者氏名",
                    value=None,  # 値なし
                    confidence_score=0.0,
                    confidence_level=ConfidenceLevel.LOW,
                ),
            ],
            validation_errors=[],
        )
        csv_bytes = csv_generator.generate(doc)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        assert df.iloc[0]["預金者氏名_チェック"] == "NG"

    def test_generate_check_columns_review_for_low_confidence(
        self, csv_generator: CsvGenerator
    ):
        """LOW confidenceフィールドのチェック結果が要確認になること"""
        doc = OcrDocument(
            file_id="FILE003",
            original_filename="test3.pdf",
            form_type=FormType.GENERAL,
            status=DocumentStatus.PROCESSING,
            fields=[
                OcrField(
                    field_name="口座番号",
                    value="1234567",
                    confidence_score=50.0,
                    confidence_level=ConfidenceLevel.LOW,
                ),
            ],
            validation_errors=[],
        )
        csv_bytes = csv_generator.generate(doc)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        assert df.iloc[0]["口座番号_チェック"] == "要確認"

    def test_generate_uses_corrected_value_when_available(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """修正値がある場合はそちらをCSVに出力する"""
        sample_document.fields[0].corrected_value = "田中太郎"

        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        assert df.iloc[0]["預金者氏名"] == "田中太郎"

    def test_generate_includes_all_csv_columns(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が全CSVカラムを含む"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

        for col in CSV_COLUMNS:
            assert col in df.columns


class TestCsvGeneratorFilename:
    """CsvGenerator.generate_filename() のテスト"""

    def test_normal_filename_format(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """通常ケース: {FileID}_{委託者番号}_{契約者番号}.csv"""
        filename = csv_generator.generate_filename(sample_document)
        assert filename == "FILE001_12345_67890.csv"

    def test_filename_with_review_marker(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """要確認マーカー付き: {★要確認_{委託者番号}_{契約者番号}.csv"""
        # 未確認のLOW confidenceフィールドを追加
        sample_document.fields.append(
            OcrField(
                field_name="口座番号",
                value="123",
                confidence_score=50.0,
                confidence_level=ConfidenceLevel.LOW,
                is_confirmed=False,
            )
        )
        filename = csv_generator.generate_filename(sample_document)
        assert filename == "★要確認_12345_67890.csv"

    def test_filename_without_review_when_low_is_confirmed(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """LOW confidenceでも確認済みの場合は★要確認なし"""
        sample_document.fields.append(
            OcrField(
                field_name="口座番号",
                value="123",
                confidence_score=50.0,
                confidence_level=ConfidenceLevel.LOW,
                is_confirmed=True,
            )
        )
        filename = csv_generator.generate_filename(sample_document)
        assert filename == "FILE001_12345_67890.csv"

    def test_filename_missing_consignor_number(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """委託者番号が欠落: UNKNOWN_{FileID}.csv"""
        sample_document.consignor_number = None
        filename = csv_generator.generate_filename(sample_document)
        assert filename == "UNKNOWN_FILE001.csv"

    def test_filename_missing_contract_number(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """契約者番号が欠落: UNKNOWN_{FileID}.csv"""
        sample_document.contract_number = None
        filename = csv_generator.generate_filename(sample_document)
        assert filename == "UNKNOWN_FILE001.csv"


class TestGenerateFilenameHelper:
    """共通ヘルパー関数 _generate_filename() のテスト"""

    def test_normal_csv(self):
        """通常CSV命名"""
        result = _generate_filename("F001", "111", "222", False, "csv")
        assert result == "F001_111_222.csv"

    def test_normal_pdf(self):
        """通常PDF命名"""
        result = _generate_filename("F001", "111", "222", False, "pdf")
        assert result == "F001_111_222.pdf"

    def test_review_csv(self):
        """要確認付きCSV命名"""
        result = _generate_filename("F001", "111", "222", True, "csv")
        assert result =★要確認_111_222.csv"

    def test_unknown_missing_consignor(self):
        """委託者番号なしでUNKNOWN"""
        result = _generate_filename("F001", None, "222", False, "csv")
        assert result == "UNKNOWN_F001.csv"

    def test_unknown_missing_contract(self):
        """契約番号なしでUNKNOWN"""
        result = _generate_filename("F001", "111", None, False, "csv")
        assert result == "UNKNOWN_F001.csv"

    def test_unknown_empty_consignor(self):
        """委託者番号空文字でUNKNOWN"""
        result = _generate_filename("F001", "", "222", False, "csv")
        assert result == "UNKNOWN_F001.csv"

    def test_unknown_empty_contract(self):
        """契約番号空文字でUNKNOWN"""
        result = _generate_filename("F001", "111", "", False, "csv")
        assert result == "UNKNOWN_F001.csv"
