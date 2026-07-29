"""
バリデーションエンジンのプロパティテスト

Property 2: 必須フィールド記入漏れ検出
**Validates: Requirements 4.1-4.6**

Hypothesisライブラリを使用し、最低100イテレーション。
ランダム生成されたOcrFieldリストに対して、check_missing_fieldsの
以下の性質を検証する:
1. 全必須フィールドが非空 → エラー0件
2. 必須フィールドが空/None → 少なくとも1件のエラー
3. エラー件数 == 空/欠損の必須フィールド数（蓄積方式）
4. 全エラーのerror_type == MISSING_FIELD
5. エラーのfield_nameは必須フィールドリストの部分集合
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.models.enums import ConfidenceLevel, FormType, ValidationErrorType
from backend.models.schemas import OcrField
from backend.services.financial_code_service import FinancialCodeService
from backend.services.validator import Validator
from backend.config import FINANCIAL_CODES_CSV_PATH


# === フィクスチャ ===


@pytest.fixture(scope="module")
def validator():
    """モジュールスコープのバリデーター（テスト高速化のため共有）"""
    fcs = FinancialCodeService(csv_path=FINANCIAL_CODES_CSV_PATH)
    return Validator(financial_code_service=fcs)


# テスト内でvalidatorを使用するためのモジュールレベルインスタンス
_fcs = FinancialCodeService(csv_path=FINANCIAL_CODES_CSV_PATH)
_validator = Validator(financial_code_service=_fcs)


# === Hypothesisストラテジー ===


@st.composite
def ocr_field_strategy(draw, field_name=None, allow_empty=True):
    """OcrFieldを生成するストラテジー"""
    name = field_name or draw(st.text(min_size=1, max_size=20))
    if allow_empty:
        value = draw(st.one_of(st.none(), st.text(min_size=0, max_size=50)))
    else:
        # 非空の値を生成（空白のみも除外）
        value = draw(
            st.text(min_size=1, max_size=50).filter(lambda v: v.strip() != "")
        )
    score = draw(st.floats(min_value=0, max_value=100))
    level = draw(st.sampled_from([ConfidenceLevel.HIGH, ConfidenceLevel.LOW]))
    return OcrField(
        field_name=name,
        value=value,
        confidence_score=score,
        confidence_level=level,
    )


@st.composite
def filled_required_fields_strategy(draw, form_type: FormType):
    """指定form_typeの全必須フィールドを非空で生成するストラテジー"""
    required = (
        Validator.GENERAL_REQUIRED_FIELDS
        if form_type == FormType.GENERAL
        else Validator.YUCHO_REQUIRED_FIELDS
    )
    fields = []
    for field_name in required:
        field = draw(ocr_field_strategy(field_name=field_name, allow_empty=False))
        fields.append(field)
    return fields


@st.composite
def partially_missing_fields_strategy(draw, form_type: FormType):
    """
    指定form_typeの必須フィールドの一部を空にするストラテジー。
    少なくとも1つは空/Noneとなることを保証する。
    """
    required = (
        Validator.GENERAL_REQUIRED_FIELDS
        if form_type == FormType.GENERAL
        else Validator.YUCHO_REQUIRED_FIELDS
    )

    # 各必須フィールドについて、記入するか空にするかをランダムに決定
    # ただし少なくとも1つは空にする
    fill_flags = draw(
        st.lists(st.booleans(), min_size=len(required), max_size=len(required))
    )
    # 少なくとも1つはFalse（空にする）ことを保証
    assume(not all(fill_flags))

    fields = []
    for field_name, should_fill in zip(required, fill_flags):
        if should_fill:
            field = draw(ocr_field_strategy(field_name=field_name, allow_empty=False))
        else:
            # 空の値を生成（None, 空文字, 空白のみのいずれか）
            empty_value = draw(st.one_of(
                st.none(),
                st.just(""),
                st.text(alphabet=" \t", min_size=1, max_size=5),
            ))
            score = draw(st.floats(min_value=0, max_value=100))
            level = draw(st.sampled_from([ConfidenceLevel.HIGH, ConfidenceLevel.LOW]))
            field = OcrField(
                field_name=field_name,
                value=empty_value,
                confidence_score=score,
                confidence_level=level,
            )
        fields.append(field)
    return fields


# === プロパティテスト ===


class TestProperty2MissingFieldDetection:
    """
    Property 2: 必須フィールド記入漏れ検出

    **Validates: Requirements 4.1-4.6**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_general_all_filled_returns_no_errors(self, data):
        """
        一般銀行様式: 全必須フィールドが非空 → check_missing_fieldsはエラー0件を返す

        **Validates: Requirements 4.1-4.6**
        """
        fields = data.draw(filled_required_fields_strategy(form_type=FormType.GENERAL))
        errors = _validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 0

    @given(data=st.data())
    @settings(max_examples=100)
    def test_yucho_all_filled_returns_no_errors(self, data):
        """
        ゆうちょ銀行様式: 全必須フィールドが非空 → check_missing_fieldsはエラー0件を返す

        **Validates: Requirements 4.1-4.6**
        """
        fields = data.draw(filled_required_fields_strategy(form_type=FormType.YUCHO))
        errors = _validator.check_missing_fields(fields, FormType.YUCHO)
        assert len(errors) == 0

    @given(data=st.data())
    @settings(max_examples=100)
    def test_missing_fields_returns_at_least_one_error(self, data):
        """
        必須フィールドの少なくとも1つが空/None → 少なくとも1件のエラーが返される

        **Validates: Requirements 4.1-4.6**
        """
        form_type = data.draw(st.sampled_from([FormType.GENERAL, FormType.YUCHO]))
        fields = data.draw(partially_missing_fields_strategy(form_type=form_type))
        errors = _validator.check_missing_fields(fields, form_type)
        assert len(errors) >= 1

    @given(data=st.data())
    @settings(max_examples=100)
    def test_error_count_equals_missing_count(self, data):
        """
        蓄積方式確認: エラー件数 == 空/欠損の必須フィールド数

        **Validates: Requirements 4.1-4.6**
        """
        form_type = data.draw(st.sampled_from([FormType.GENERAL, FormType.YUCHO]))
        required = (
            Validator.GENERAL_REQUIRED_FIELDS
            if form_type == FormType.GENERAL
            else Validator.YUCHO_REQUIRED_FIELDS
        )

        # ランダムに各必須フィールドの記入/未記入を決定
        fields = []
        expected_missing_count = 0
        for field_name in required:
            should_fill = data.draw(st.booleans())
            if should_fill:
                field = data.draw(
                    ocr_field_strategy(field_name=field_name, allow_empty=False)
                )
            else:
                empty_value = data.draw(st.one_of(
                    st.none(),
                    st.just(""),
                    st.text(alphabet=" \t", min_size=1, max_size=5),
                ))
                score = data.draw(st.floats(min_value=0, max_value=100))
                level = data.draw(
                    st.sampled_from([ConfidenceLevel.HIGH, ConfidenceLevel.LOW])
                )
                field = OcrField(
                    field_name=field_name,
                    value=empty_value,
                    confidence_score=score,
                    confidence_level=level,
                )
                expected_missing_count += 1
            fields.append(field)

        errors = _validator.check_missing_fields(fields, form_type)
        assert len(errors) == expected_missing_count

    @given(data=st.data())
    @settings(max_examples=100)
    def test_all_errors_have_missing_field_type(self, data):
        """
        全返却エラーのerror_type == ValidationErrorType.MISSING_FIELD

        **Validates: Requirements 4.6**
        """
        form_type = data.draw(st.sampled_from([FormType.GENERAL, FormType.YUCHO]))
        fields = data.draw(partially_missing_fields_strategy(form_type=form_type))
        errors = _validator.check_missing_fields(fields, form_type)
        for error in errors:
            assert error.error_type == ValidationErrorType.MISSING_FIELD

    @given(data=st.data())
    @settings(max_examples=100)
    def test_error_field_names_subset_of_required(self, data):
        """
        エラーのfield_nameは常に当該form_typeの必須フィールドリストの部分集合

        **Validates: Requirements 4.1-4.6**
        """
        form_type = data.draw(st.sampled_from([FormType.GENERAL, FormType.YUCHO]))
        required = (
            Validator.GENERAL_REQUIRED_FIELDS
            if form_type == FormType.GENERAL
            else Validator.YUCHO_REQUIRED_FIELDS
        )

        # 任意のフィールドリスト（必須フィールドとランダムフィールドの混合）
        fields = data.draw(partially_missing_fields_strategy(form_type=form_type))
        # オプショナルな追加フィールドも混ぜる
        extra_fields = data.draw(
            st.lists(ocr_field_strategy(), min_size=0, max_size=3)
        )
        all_fields = fields + extra_fields

        errors = _validator.check_missing_fields(all_fields, form_type)
        error_field_names = {e.field_name for e in errors}
        assert error_field_names.issubset(set(required))

    @given(data=st.data())
    @settings(max_examples=100)
    def test_missing_field_not_in_list_treated_as_missing(self, data):
        """
        必須フィールドがfieldsリストに存在しない場合も記入漏れとして検出される

        **Validates: Requirements 4.1-4.6**
        """
        form_type = data.draw(st.sampled_from([FormType.GENERAL, FormType.YUCHO]))
        required = (
            Validator.GENERAL_REQUIRED_FIELDS
            if form_type == FormType.GENERAL
            else Validator.YUCHO_REQUIRED_FIELDS
        )

        # 一部の必須フィールドを意図的にリストから除外
        num_to_remove = data.draw(st.integers(min_value=1, max_value=len(required)))
        indices_to_keep = sorted(
            data.draw(
                st.lists(
                    st.integers(min_value=0, max_value=len(required) - 1),
                    min_size=len(required) - num_to_remove,
                    max_size=len(required) - num_to_remove,
                    unique=True,
                )
            )
        )

        fields = []
        for i in indices_to_keep:
            field = data.draw(
                ocr_field_strategy(field_name=required[i], allow_empty=False)
            )
            fields.append(field)

        errors = _validator.check_missing_fields(fields, form_type)
        # 除外したフィールド分のエラーが発生する
        assert len(errors) == num_to_remove
