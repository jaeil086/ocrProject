"""
書類仕分けロジックのプロパティテスト

Property 6: 書類仕分けの網羅性と排他性
Property 7: Confidence Score閾値判定

Validates: Requirements 10.1-10.3, 6.1
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.enums import ConfidenceLevel, DocumentStatus, ValidationErrorType
from backend.models.schemas import OcrField, ValidationError
from backend.services.document_classifier import DocumentClassifier


# === テスト用ストラテジー ===


@st.composite
def ocr_field_strategy(draw):
    """任意のOcrFieldを生成するストラテジー"""
    field_name = draw(st.text(min_size=1, max_size=20))
    value = draw(st.one_of(st.none(), st.text(min_size=0, max_size=50)))
    score = draw(st.floats(min_value=0, max_value=100, allow_nan=False))
    level = draw(st.sampled_from([ConfidenceLevel.HIGH, ConfidenceLevel.LOW]))
    is_confirmed = draw(st.booleans())
    return OcrField(
        field_name=field_name,
        value=value,
        confidence_score=score,
        confidence_level=level,
        is_confirmed=is_confirmed,
    )


@st.composite
def validation_error_strategy(draw):
    """任意のValidationErrorを生成するストラテジー"""
    field_name = draw(st.text(min_size=1, max_size=20))
    error_type = draw(st.sampled_from(list(ValidationErrorType)))
    message = draw(st.text(min_size=1, max_size=100))
    return ValidationError(field_name=field_name, error_type=error_type, message=message)


# === Property 6: 書類仕分けの網羅性と排他性 ===


class TestClassifierExhaustivenessAndExclusivity:
    """
    Property 6: 書類仕分けの網羅性と排他性

    任意のフィールドとバリデーションエラーの組み合わせに対して、
    classify()は必ず NORMAL, DEFICIENT, NEEDS_REVIEW のいずれか1つを返す。

    **Validates: Requirements 10.1-10.3**
    """

    @given(
        fields=st.lists(ocr_field_strategy(), min_size=0, max_size=10),
        errors=st.lists(validation_error_strategy(), min_size=0, max_size=5),
    )
    @settings(max_examples=200)
    def test_classify_always_returns_valid_status(self, fields, errors):
        """classify()は常に有効なDocumentStatusを返す"""
        classifier = DocumentClassifier()
        result = classifier.classify(fields=fields, validation_errors=errors)

        # 結果は必ず3つのステータスのいずれかである
        valid_statuses = {
            DocumentStatus.NORMAL,
            DocumentStatus.DEFICIENT,
            DocumentStatus.NEEDS_REVIEW,
        }
        assert result in valid_statuses, (
            f"classify()が無効なステータスを返しました: {result}"
        )

    @given(
        fields=st.lists(ocr_field_strategy(), min_size=0, max_size=10),
        errors=st.lists(validation_error_strategy(), min_size=0, max_size=5),
    )
    @settings(max_examples=200)
    def test_classify_is_deterministic(self, fields, errors):
        """同じ入力に対して常に同じ結果を返す（決定性）"""
        classifier = DocumentClassifier()
        result1 = classifier.classify(fields=fields, validation_errors=errors)
        result2 = classifier.classify(fields=fields, validation_errors=errors)
        assert result1 == result2, (
            f"同じ入力に対して異なる結果: {result1} != {result2}"
        )


# === Property 7: Confidence Score閾値判定 ===


class TestConfidenceScoreThresholdDecision:
    """
    Property 7: Confidence Score閾値判定

    バリデーションエラーの有無とConfidence Levelの組み合わせに基づく
    正確な分類ルールの検証。

    **Validates: Requirements 10.1-10.3, 6.1**
    """

    @given(
        fields=st.lists(ocr_field_strategy(), min_size=0, max_size=10),
        errors=st.lists(validation_error_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=200)
    def test_with_errors_always_deficient(self, fields, errors):
        """バリデーションエラーが存在する場合、常にDEFICIENT"""
        classifier = DocumentClassifier()
        result = classifier.classify(fields=fields, validation_errors=errors)
        assert result == DocumentStatus.DEFICIENT, (
            f"エラーがある場合はDEFICIENTであるべき: got {result}, "
            f"errors={errors}"
        )

    @given(
        fields=st.lists(
            ocr_field_strategy().filter(
                lambda f: f.confidence_level == ConfidenceLevel.HIGH or f.is_confirmed
            ),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=200)
    def test_no_errors_all_high_or_confirmed_is_normal(self, fields):
        """エラーなし + 全フィールドがHIGHまたは確認済み → NORMAL"""
        classifier = DocumentClassifier()
        result = classifier.classify(fields=fields, validation_errors=[])
        assert result == DocumentStatus.NORMAL, (
            f"エラーなし+全HIGH/確認済みの場合はNORMALであるべき: got {result}, "
            f"fields={[(f.field_name, f.confidence_level, f.is_confirmed) for f in fields]}"
        )

    @given(
        high_fields=st.lists(
            ocr_field_strategy().filter(
                lambda f: f.confidence_level == ConfidenceLevel.HIGH
            ),
            min_size=0,
            max_size=5,
        ),
        low_unconfirmed_fields=st.lists(
            ocr_field_strategy().filter(
                lambda f: f.confidence_level == ConfidenceLevel.LOW
                and not f.is_confirmed
            ),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=200)
    def test_no_errors_with_low_unconfirmed_is_needs_review(
        self, high_fields, low_unconfirmed_fields
    ):
        """エラーなし + 未確認LOWフィールドあり → NEEDS_REVIEW"""
        classifier = DocumentClassifier()
        all_fields = high_fields + low_unconfirmed_fields
        result = classifier.classify(fields=all_fields, validation_errors=[])
        assert result == DocumentStatus.NEEDS_REVIEW, (
            f"エラーなし+未確認LOWフィールドありの場合はNEEDS_REVIEWであるべき: got {result}, "
            f"fields={[(f.field_name, f.confidence_level, f.is_confirmed) for f in all_fields]}"
        )

    @given(
        fields=st.lists(
            ocr_field_strategy().filter(
                lambda f: f.confidence_level == ConfidenceLevel.LOW
                and not f.is_confirmed
            ),
            min_size=1,
            max_size=5,
        ),
        errors=st.lists(validation_error_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=200)
    def test_deficient_takes_priority_over_needs_review(self, fields, errors):
        """DEFICIENTはNEEDS_REVIEWより優先される"""
        classifier = DocumentClassifier()
        result = classifier.classify(fields=fields, validation_errors=errors)
        assert result == DocumentStatus.DEFICIENT, (
            f"DEFICIENTはNEEDS_REVIEWより優先されるべき: got {result}, "
            f"errors={errors}, "
            f"fields={[(f.field_name, f.confidence_level, f.is_confirmed) for f in fields]}"
        )
