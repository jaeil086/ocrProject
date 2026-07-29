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
        新3カテゴリ体系でのバリデーション

        - カテゴリ1: 〇印チェック — 「未選択」「なし」はエラー
        - カテゴリ2: 未入力チェック — 「未記入」はエラー
        - カテゴリ3: 契約者番号が読み取れなかったらエラー
        """
        errors: list[ValidationError] = []
        field_map = {f.field_name: f for f in fields}

        # カテゴリ1: 〇印チェック
        agency = field_map.get("収納代行会社名")
        if agency and agency.value == "未選択":
            errors.append(ValidationError(
                field_name="収納代行会社名",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="収納代行会社名に〇印がありません",
            ))

        deposit = field_map.get("預金種目")
        if deposit and deposit.value == "未選択":
            errors.append(ValidationError(
                field_name="預金種目",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="預金種目に〇印がありません",
            ))

        seal = field_map.get("届出印")
        if seal and seal.value == "なし":
            errors.append(ValidationError(
                field_name="届出印",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="届出印が押印されていません",
            ))

        # カテゴリ2: 未入力チェック
        input_fields = ["預金者名フリガナ", "預金者名氏名", "口座番号", "記号番号"]
        for name in input_fields:
            field = field_map.get(name)
            if field and field.value == "未記入":
                errors.append(ValidationError(
                    field_name=name,
                    error_type=ValidationErrorType.MISSING_FIELD,
                    message=f"{name}が記入されていません",
                ))

        # カテゴリ3: 契約者番号が未取得
        contract = field_map.get("契約者番号")
        if not contract or not contract.value or contract.value.strip() == "":
            errors.append(ValidationError(
                field_name="契約者番号",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="契約者番号が読み取れません",
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
