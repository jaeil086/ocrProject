"""
CSV生成サービスのテスト

CsvGenerator.generate() と CsvGenerator.generate_filename() の動作を検証する。
"""

import io

import pandas as pd
import pytest

from backend.models.enums import (
    ConfidenceLevel,
    DocumentStatus,
    FormType,
    ValidationErrorType,
)
from backend.models.schemas import OcrDocument, OcrField, ValidationError
from backend.services.csv_generator import CsvGenerator, _generate_filename


@pytest.fixture
def csv_generator():
    """CsvGeneratorインスタンスを生成"""
    return CsvGenerator()


@pytest.fixture
def sample_document():
    """テスト用OcrDocumentを生成"""
    return OcrDocument(
        file_id="FILE001",
        original_filename="test.pdf",
        form_type=FormType.GENERAL,
        status=DocumentStatus.NORMAL,
        consignor_number="12345",
        contract_number="67890",
        fields=[
            OcrField(
                field_name="預金者名（フリガナ）",
                value="ヤマダ タロウ",
                confidence_score=95.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
            OcrField(
                field_name="預金者名（氏名）",
                value="山田太郎",
                confidence_score=90.0,
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
                field_name="口座番号",
                value="1234567",
                confidence_score=92.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ],
        validation_errors=[],
    )


class TestCsvGeneratorGenerate:
    """CsvGenerator.generate() のテスト"""

    def test_generate_produces_valid_shift_jis_csv(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()がShift_JISエンコードの有効なCSVを生成する"""
        csv_bytes = csv_generator.generate(sample_document)

        # Shift_JISでデコード可能であること
        csv_text = csv_bytes.decode("shift_jis")

        # CSVとしてパース可能であること
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")
        assert len(df) == 1

        # ヘッダーにFileIDが含まれること
        assert "FileID" in df.columns
        assert df.iloc[0]["FileID"] == "FILE001"

    def test_generate_includes_japanese_field_values(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が日本語フィールド値を正しくCSVに含める"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")

        assert df.iloc[0]["預金者名（フリガナ）"] == "ヤマダ タロウ"
        assert df.iloc[0]["預金者名（氏名）"] == "山田太郎"
        assert df.iloc[0]["銀行名"] == "みずほ銀行"

    def test_generate_uses_corrected_value_when_available(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """修正値がある場合はそちらをCSVに出力する"""
        # 修正値を設定
        sample_document.fields[0].corrected_value = "ヤマダ ジロウ"

        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")

        assert df.iloc[0]["預金者名（フリガナ）"] == "ヤマダ ジロウ"

    def test_generate_with_validation_errors_in_remarks(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """バリデーションエラーが備考列に記録される"""
        sample_document.validation_errors = [
            ValidationError(
                field_name="銀行番号",
                error_type=ValidationErrorType.BANK_CODE_NOT_FOUND,
                message="銀行番号 9999 は存在しません",
            ),
            ValidationError(
                field_name="口座番号",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="口座番号が記入されていません",
            ),
        ]

        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")

        remarks = df.iloc[0]["備考"]
        assert "銀行番号" in remarks
        assert "銀行番号 9999 は存在しません" in remarks
        assert "口座番号" in remarks
        assert "口座番号が記入されていません" in remarks

    def test_generate_empty_remarks_when_no_errors(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """バリデーションエラーがない場合、備考列は空"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")

        # pandasはNaN/空文字列を読み込む場合がある
        remarks = df.iloc[0]["備考"]
        assert pd.isna(remarks) or remarks == ""

    def test_generate_includes_all_csv_columns(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """generate()が全CSVカラムを含む"""
        csv_bytes = csv_generator.generate(sample_document)
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="shift_jis")

        expected_columns = [
            "FileID",
            "様式区分",
            "委託者番号",
            "契約番号",
            "預金者名（フリガナ）",
            "預金者名（氏名）",
            "銀行名",
            "支店名",
            "銀行番号",
            "店番号",
            "口座番号",
            "預金種目",
            "金融機関種別",
            "会社名",
            "肩書き",
            "代表者名",
            "振替明細記入欄",
            "加算月記入欄",
            "ステータス",
            "備考",
        ]
        for col in expected_columns:
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
        """要確認マーカー付き: {FileID}_★要確認_{委託者番号}_{契約者番号}.csv"""
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
        assert filename == "FILE001_★要確認_12345_67890.csv"

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
                is_confirmed=True,  # 確認済み
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

    def test_filename_missing_both_numbers(
        self, csv_generator: CsvGenerator, sample_document: OcrDocument
    ):
        """委託者番号・契約者番号両方欠落: UNKNOWN_{FileID}.csv"""
        sample_document.consignor_number = None
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
        assert result == "F001_★要確認_111_222.csv"

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
