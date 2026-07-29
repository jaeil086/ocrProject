"""
書類仕分けロジックのテスト

DocumentClassifier.classify() の分類ロジックを検証する。
"""

import pytest

from backend.models.enums import ConfidenceLevel, DocumentStatus, ValidationErrorType
from backend.models.schemas import OcrField, ValidationError
from backend.services.document_classifier import DocumentClassifier


@pytest.fixture
def classifier():
    """DocumentClassifierインスタンスを返す"""
    return DocumentClassifier()


def _make_field(
    field_name: str = "test_field",
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH,
    is_confirmed: bool = False,
) -> OcrField:
    """テスト用OcrFieldを生成するヘルパー"""
    return OcrField(
        field_name=field_name,
        value="テスト値",
        confidence_score=95.0 if confidence_level == ConfidenceLevel.HIGH else 40.0,
        confidence_level=confidence_level,
        is_confirmed=is_confirmed,
    )


def _make_validation_error(field_name: str = "test_field") -> ValidationError:
    """テスト用ValidationErrorを生成するヘルパー"""
    return ValidationError(
        field_name=field_name,
        error_type=ValidationErrorType.MISSING_FIELD,
        message="記入漏れがあります",
    )


class TestDocumentClassifierNormal:
    """NORMAL判定のテスト"""

    def test_empty_errors_all_high_confidence(self, classifier):
        """バリデーションエラーなし + 全フィールドHIGH → NORMAL"""
        fields = [
            _make_field("bank_code", ConfidenceLevel.HIGH),
            _make_field("branch_code", ConfidenceLevel.HIGH),
            _make_field("account_number", ConfidenceLevel.HIGH),
        ]
        result = classifier.classify(fields=fields, validation_errors=[])
        assert result == DocumentStatus.NORMAL

    def test_empty_fields_and_empty_errors(self, classifier):
        """フィールドもエラーも空 → NORMAL"""
        result = classifier.classify(fields=[], validation_errors=[])
        assert result == DocumentStatus.NORMAL

    def test_low_confidence_but_confirmed(self, classifier):
        """LOW confidence + 確認済み → NORMAL（確認済みフラグで上書き）"""
        fields = [
            _make_field("bank_code", ConfidenceLevel.HIGH),
            _make_field("account_number", ConfidenceLevel.LOW, is_confirmed=True),
        ]
        result = classifier.classify(fields=fields, validation_errors=[])
        assert result == DocumentStatus.NORMAL


class TestDocumentClassifierDeficient:
    """DEFICIENT判定のテスト"""

    def test_non_empty_errors(self, classifier):
        """バリデーションエラーあり → DEFICIENT"""
        fields = [_make_field("bank_code", ConfidenceLevel.HIGH)]
        errors = [_make_validation_error("bank_code")]
        result = classifier.classify(fields=fields, validation_errors=errors)
        assert result == DocumentStatus.DEFICIENT

    def test_errors_take_priority_over_low_confidence(self, classifier):
        """エラーありかつLOW confidenceあり → DEFICIENT（エラーが優先）"""
        fields = [
            _make_field("bank_code", ConfidenceLevel.LOW, is_confirmed=False),
        ]
        errors = [_make_validation_error("bank_code")]
        result = classifier.classify(fields=fields, validation_errors=errors)
        assert result == DocumentStatus.DEFICIENT


class TestDocumentClassifierNeedsReview:
    """NEEDS_REVIEW判定のテスト"""

    def test_low_confidence_not_confirmed(self, classifier):
        """LOW confidence + 未確認 → NEEDS_REVIEW"""
        fields = [
            _make_field("bank_code", ConfidenceLevel.HIGH),
            _make_field("account_number", ConfidenceLevel.LOW, is_confirmed=False),
        ]
        result = classifier.classify(fields=fields, validation_errors=[])
        assert result == DocumentStatus.NEEDS_REVIEW

    def test_multiple_low_confidence_fields(self, classifier):
        """複数のLOW confidenceフィールド → NEEDS_REVIEW"""
        fields = [
            _make_field("bank_code", ConfidenceLevel.LOW, is_confirmed=False),
            _make_field("branch_code", ConfidenceLevel.LOW, is_confirmed=False),
        ]
        result = classifier.classify(fields=fields, validation_errors=[])
        assert result == DocumentStatus.NEEDS_REVIEW
