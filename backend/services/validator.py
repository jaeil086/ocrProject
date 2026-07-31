"""
バリデーションエンジン

OCR抽出結果に対して、記入漏れチェックを行う。
"""

from backend.models.enums import FormType, ValidationErrorType
from backend.models.schemas import OcrField, ValidationError


class Validator:
    """バリデーションエンジン（新3カテゴリ体系）"""

    def __init__(self):
        pass

    def check_missing_fields(
        self, fields: list[OcrField], form_type: FormType
    ) -> list[ValidationError]:
        """
        2段階OCR体系でのバリデーション
        実際の文字列を返す方式のため、nullのフィールドをエラーとする
        """
        errors: list[ValidationError] = []
        field_map = {f.field_name: f for f in fields}

        # 届出印チェック
        seal = field_map.get("届出印")
        if seal and seal.value == "なし":
            errors.append(ValidationError(
                field_name="届出印",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="届出印が押印されていません",
            ))

        # null（読み取り不可）フィールドをエラーとする
        required_fields = [
            "預金者名フリガナ", "預金者名氏名", "口座番号",
            "銀行番号", "支店番号", "契約者番号"
        ]
        for name in required_fields:
            field = field_map.get(name)
            if not field or not field.value:
                errors.append(ValidationError(
                    field_name=name,
                    error_type=ValidationErrorType.MISSING_FIELD,
                    message=f"{name}が読み取れません",
                ))

        return errors

    def check_financial_codes(
        self, fields: list[OcrField]
    ) -> list[ValidationError]:
        """金融機関コード実在チェック（単純にOCR認識のみのため省略）"""
        return []

    def complement_codes(self, fields: list[OcrField]) -> list[OcrField]:
        """コード補完（省略）"""
        return fields
