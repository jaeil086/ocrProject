"""
バリデーションエンジンのユニットテスト

Validator.check_missing_fields(), check_financial_codes(), complement_codes() を検証する。
"""

import pytest

from backend.models.enums import ConfidenceLevel, FormType, ValidationErrorType
from backend.models.schemas import OcrField, ValidationError
from backend.services.financial_code_service import FinancialCodeService
from backend.services.validator import Validator


@pytest.fixture
def financial_code_service():
    """テスト用金融機関コードサービス（実CSVを使用）"""
    from backend.config import FINANCIAL_CODES_CSV_PATH
    return FinancialCodeService(csv_path=FINANCIAL_CODES_CSV_PATH)


@pytest.fixture
def validator(financial_code_service):
    """テスト用バリデーター"""
    return Validator(financial_code_service=financial_code_service)


def _make_field(name: str, value: str = "テスト値") -> OcrField:
    """テスト用OcrFieldヘルパー"""
    return OcrField(
        field_name=name,
        value=value,
        confidence_score=90.0,
        confidence_level=ConfidenceLevel.HIGH,
    )


# === check_missing_fields テスト ===


class TestCheckMissingFields:
    """記入漏れチェックのテスト"""

    def test_general_all_filled(self, validator):
        """一般銀行様式: 全必須フィールドが記入済み → エラーなし"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("銀行名", "みずほ銀行"),
            _make_field("支店名", "東京営業部"),
            _make_field("口座番号", "1234567"),
        ]
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 0

    def test_general_missing_one(self, validator):
        """一般銀行様式: 1件記入漏れ → エラー1件"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("銀行名", "みずほ銀行"),
            _make_field("支店名", "東京営業部"),
            _make_field("口座番号", ""),  # 空文字
        ]
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 1
        assert errors[0].field_name == "口座番号"
        assert errors[0].error_type == ValidationErrorType.MISSING_FIELD

    def test_general_missing_all(self, validator):
        """一般銀行様式: 全必須フィールドが空 → エラー5件"""
        fields = []
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 5

    def test_general_none_value(self, validator):
        """一般銀行様式: valueがNone → 記入漏れ"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("銀行名", "みずほ銀行"),
            _make_field("支店名", "東京営業部"),
            OcrField(
                field_name="口座番号",
                value=None,
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ]
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 1
        assert errors[0].field_name == "口座番号"

    def test_general_whitespace_only(self, validator):
        """一般銀行様式: 空白のみ → 記入漏れ"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("銀行名", "みずほ銀行"),
            _make_field("支店名", "   "),  # 空白のみ
            _make_field("口座番号", "1234567"),
        ]
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 1
        assert errors[0].field_name == "支店名"

    def test_yucho_all_filled(self, validator):
        """ゆうちょ銀行様式: 全必須フィールドが記入済み → エラーなし"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("記号", "10100"),
            _make_field("番号", "12345671"),
        ]
        errors = validator.check_missing_fields(fields, FormType.YUCHO)
        assert len(errors) == 0

    def test_yucho_missing_fields(self, validator):
        """ゆうちょ銀行様式: 記号・番号が空 → エラー2件"""
        fields = [
            _make_field("預金者名（フリガナ）", "ヤマダタロウ"),
            _make_field("預金者名（氏名）", "山田太郎"),
            _make_field("記号", ""),
            _make_field("番号", ""),
        ]
        errors = validator.check_missing_fields(fields, FormType.YUCHO)
        assert len(errors) == 2

    def test_accumulation_mode(self, validator):
        """蓄積方式: 複数エラーが全件収集される"""
        fields = [
            _make_field("預金者名（フリガナ）", ""),
            _make_field("預金者名（氏名）", ""),
            _make_field("銀行名", ""),
            _make_field("支店名", ""),
            _make_field("口座番号", ""),
        ]
        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 5
        # 全必須フィールドがエラーとして返される
        error_fields = {e.field_name for e in errors}
        assert error_fields == {
            "預金者名（フリガナ）",
            "預金者名（氏名）",
            "銀行名",
            "支店名",
            "口座番号",
        }


# === check_financial_codes テスト ===


class TestCheckFinancialCodes:
    """金融機関コード整合性チェックのテスト"""

    def test_valid_bank_code(self, validator):
        """銀行番号が実在する → エラーなし"""
        fields = [_make_field("銀行番号", "0001")]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_invalid_bank_code(self, validator):
        """銀行番号が存在しない → 不存在エラー"""
        fields = [_make_field("銀行番号", "9999")]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 1
        assert errors[0].error_type == ValidationErrorType.BANK_CODE_NOT_FOUND

    def test_bank_code_name_match(self, validator):
        """銀行番号と銀行名が一致 → エラーなし"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("銀行名", "みずほ銀行"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_bank_code_name_mismatch(self, validator):
        """銀行番号と銀行名が不一致 → 不一致エラー"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("銀行名", "三菱UFJ銀行"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 1
        assert errors[0].error_type == ValidationErrorType.BANK_CODE_MISMATCH

    def test_valid_branch_code(self, validator):
        """店番号が実在する → エラーなし"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("店番号", "001"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_invalid_branch_code(self, validator):
        """店番号が存在しない → 不存在エラー"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("店番号", "999"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 1
        assert errors[0].error_type == ValidationErrorType.BRANCH_CODE_NOT_FOUND

    def test_branch_code_name_match(self, validator):
        """店番号と支店名が一致 → エラーなし"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("店番号", "001"),
            _make_field("支店名", "東京営業部"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_branch_code_name_mismatch(self, validator):
        """店番号と支店名が不一致 → 不一致エラー"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("店番号", "001"),
            _make_field("支店名", "新宿支店"),
        ]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 1
        assert errors[0].error_type == ValidationErrorType.BRANCH_CODE_MISMATCH

    def test_no_financial_codes(self, validator):
        """金融機関コードフィールドがない → エラーなし"""
        fields = [_make_field("預金者名（氏名）", "山田太郎")]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_empty_bank_code(self, validator):
        """銀行番号が空文字 → チェックスキップ、エラーなし"""
        fields = [_make_field("銀行番号", "")]
        errors = validator.check_financial_codes(fields)
        assert len(errors) == 0

    def test_multiple_errors_accumulated(self, validator):
        """銀行番号不存在 + 店番号不存在 → エラー2件（蓄積方式）"""
        fields = [
            _make_field("銀行番号", "9999"),
            _make_field("店番号", "999"),
        ]
        errors = validator.check_financial_codes(fields)
        # 銀行番号不存在のため、店番号はbranch_code_exists_anyで検索
        assert len(errors) >= 1
        error_types = {e.error_type for e in errors}
        assert ValidationErrorType.BANK_CODE_NOT_FOUND in error_types


# === complement_codes テスト ===


class TestComplementCodes:
    """金融機関コード補完のテスト"""

    def test_complement_bank_code(self, validator):
        """銀行名から銀行番号を補完"""
        fields = [
            _make_field("銀行名", "みずほ銀行"),
            OcrField(
                field_name="銀行番号",
                value=None,
                confidence_score=0.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ]
        result = validator.complement_codes(fields)
        # 銀行番号が補完されている
        bank_code_field = next(
            f for f in result if f.field_name == "銀行番号"
        )
        assert bank_code_field.value == "0001"

    def test_complement_branch_code(self, validator):
        """支店名 + 銀行番号から店番号を補完"""
        fields = [
            _make_field("銀行番号", "0001"),
            _make_field("支店名", "東京営業部"),
            OcrField(
                field_name="店番号",
                value=None,
                confidence_score=0.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ]
        result = validator.complement_codes(fields)
        branch_code_field = next(
            f for f in result if f.field_name == "店番号"
        )
        assert branch_code_field.value == "001"

    def test_complement_both_codes(self, validator):
        """銀行名・支店名から銀行番号・店番号の両方を補完"""
        fields = [
            _make_field("銀行名", "みずほ銀行"),
            _make_field("支店名", "新宿支店"),
        ]
        result = validator.complement_codes(fields)
        bank_code_field = next(
            f for f in result if f.field_name == "銀行番号"
        )
        branch_code_field = next(
            f for f in result if f.field_name == "店番号"
        )
        assert bank_code_field.value == "0001"
        assert branch_code_field.value == "009"

    def test_no_complement_when_code_exists(self, validator):
        """銀行番号が既にある → 補完しない"""
        fields = [
            _make_field("銀行名", "みずほ銀行"),
            _make_field("銀行番号", "0005"),
        ]
        result = validator.complement_codes(fields)
        bank_code_field = next(
            f for f in result if f.field_name == "銀行番号"
        )
        # 元の値が維持される
        assert bank_code_field.value == "0005"

    def test_no_complement_unknown_name(self, validator):
        """マスタに存在しない銀行名 → 補完しない"""
        fields = [
            _make_field("銀行名", "存在しない銀行"),
            OcrField(
                field_name="銀行番号",
                value=None,
                confidence_score=0.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ]
        result = validator.complement_codes(fields)
        bank_code_field = next(
            f for f in result if f.field_name == "銀行番号"
        )
        # 補完されないのでNoneのまま
        assert bank_code_field.value is None

    def test_no_complement_branch_without_bank_code(self, validator):
        """銀行番号なし + 支店名あり → 店番号は補完しない"""
        fields = [
            _make_field("支店名", "東京営業部"),
            OcrField(
                field_name="店番号",
                value=None,
                confidence_score=0.0,
                confidence_level=ConfidenceLevel.HIGH,
            ),
        ]
        result = validator.complement_codes(fields)
        branch_code_field = next(
            f for f in result if f.field_name == "店番号"
        )
        # 銀行番号が不明のため補完できない
        assert branch_code_field.value is None

    def test_complement_adds_new_field_when_missing(self, validator):
        """銀行番号フィールドが存在しない場合、新規作成して補完"""
        fields = [
            _make_field("銀行名", "みずほ銀行"),
        ]
        result = validator.complement_codes(fields)
        bank_code_fields = [f for f in result if f.field_name == "銀行番号"]
        assert len(bank_code_fields) == 1
        assert bank_code_fields[0].value == "0001"
        assert bank_code_fields[0].confidence_score == 100.0
