"""
バリデーションエンジン

OCR抽出結果に対して、記入漏れチェックおよび
金融機関マスターとの照合・交差検証を行う。
"""

import logging
from typing import Optional

from backend.models.enums import FormType, ValidationErrorType
from backend.models.schemas import MasterMatchInfo, OcrField, ValidationError
from backend.services.zengin_master import ZenginMasterService

logger = logging.getLogger(__name__)


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
        seal = field_map.get("お届出印金融機関")
        if seal and seal.value == "なし":
            errors.append(ValidationError(
                field_name="お届出印金融機関",
                error_type=ValidationErrorType.MISSING_FIELD,
                message="届出印が押印されていません",
            ))

        # ゆうちょ銀行利用判定（記号or番号に値があればゆうちょ利用）
        has_yucho = any(
            (f := field_map.get(fn)) and f.value
            for fn in ("ゆうちょ記号", "ゆうちょ番号")
        )
        # 銀行側利用判定
        has_bank = any(
            (f := field_map.get(fn)) and f.value
            for fn in ("銀行名", "支店名", "口座番号")
        )

        # null（読み取り不可）フィールドをエラーとする
        # 基本の必須フィールド
        required_fields = ["預金者フリガナ", "預金者氏名", "契約者番号"]

        # 銀行系フィールドはゆうちょ利用時は必須としない
        if not has_yucho:
            required_fields.extend(["口座番号", "銀行番号", "店番号"])

        # ゆうちょ系フィールドは銀行利用時は必須としない
        if not has_bank:
            required_fields.extend(["ゆうちょ記号", "ゆうちょ番号"])

        for name in required_fields:
            field = field_map.get(name)
            if not field or not field.value:
                errors.append(ValidationError(
                    field_name=name,
                    error_type=ValidationErrorType.MISSING_FIELD,
                    message=f"{name}が読み取れません",
                ))

        return errors

    async def check_financial_codes(
        self, fields: list[OcrField]
    ) -> list[ValidationError]:
        """
        金融機関マスターとの照合・交差検証を実行し、
        各フィールドに master_match 情報を付与する。

        検証対象: 銀行名、銀行番号、支店名、店番号
        交差検証: 銀行名↔銀行番号、支店名↔店番号

        Returns:
            ValidationErrorリスト（交差検証不一致の場合に追加）
        """
        errors: list[ValidationError] = []

        if not ZenginMasterService.is_initialized():
            logger.warning("ZenginMasterService未初期化のため金融機関検証をスキップ")
            return errors

        master = ZenginMasterService.get_instance()
        field_map = {f.field_name: f for f in fields}

        # ゆうちょ利用時は銀行マスター検証をスキップ
        has_yucho = any(
            (f := field_map.get(fn)) and f.value
            for fn in ("ゆうちょ記号", "ゆうちょ番号")
        )
        if has_yucho:
            logger.debug("ゆうちょ利用のため銀行マスター検証スキップ")
            return errors

        # === 銀行名マスター照合 ===
        bank_name_field = field_map.get("銀行名")
        bank_code_field = field_map.get("銀行番号")
        ocr_bank_name = bank_name_field.value if bank_name_field else None
        ocr_bank_code = bank_code_field.value if bank_code_field else None

        resolved_bank_code: Optional[str] = None  # 支店検索用に確定した銀行コード

        if ocr_bank_name:
            # 銀行名をマスターと照合
            bank_match = master.match_bank(ocr_bank_name)
            bank_name_field.master_match = bank_match

            if bank_match.master_code:
                resolved_bank_code = bank_match.master_code

            # 銀行名↔銀行番号 交差検証
            if ocr_bank_code:
                cross_status = master.cross_check_bank_code(
                    ocr_bank_name, ocr_bank_code
                )
                bank_name_field.master_match.cross_check_status = cross_status

                if cross_status == "mismatch":
                    errors.append(ValidationError(
                        field_name="銀行番号",
                        error_type=ValidationErrorType.BANK_CODE_MISMATCH,
                        message=f"銀行名「{ocr_bank_name}」と銀行番号「{ocr_bank_code}」が一致しません",
                    ))

        # 銀行番号フィールドにもマスター情報を付与
        if bank_code_field and ocr_bank_code:
            bank_info = master.get_bank_by_code(ocr_bank_code)
            if bank_info:
                bank_code_field.master_match = MasterMatchInfo(
                    master_value=bank_info.name,
                    master_code=bank_info.code,
                    match_score=100.0,
                    match_status="ok",
                )
                # 銀行名が空だが銀行番号からコードを解決できた場合
                if not resolved_bank_code:
                    resolved_bank_code = ocr_bank_code
            else:
                bank_code_field.master_match = MasterMatchInfo(
                    match_score=0.0,
                    match_status="ng",
                )
                errors.append(ValidationError(
                    field_name="銀行番号",
                    error_type=ValidationErrorType.BANK_CODE_NOT_FOUND,
                    message=f"銀行番号「{ocr_bank_code}」はマスターに存在しません",
                ))

        # === 支店名マスター照合 ===
        branch_name_field = field_map.get("支店名")
        branch_code_field = field_map.get("店番号")
        ocr_branch_name = branch_name_field.value if branch_name_field else None
        ocr_branch_code = branch_code_field.value if branch_code_field else None

        if ocr_branch_name and resolved_bank_code:
            # 支店名をマスターと照合
            branch_match = await master.match_branch(
                resolved_bank_code, ocr_branch_name
            )
            branch_name_field.master_match = branch_match

            # 支店名↔店番号 交差検証
            if ocr_branch_code:
                cross_status = await master.cross_check_branch_code(
                    resolved_bank_code, ocr_branch_name, ocr_branch_code
                )
                branch_name_field.master_match.cross_check_status = cross_status

                if cross_status == "mismatch":
                    errors.append(ValidationError(
                        field_name="店番号",
                        error_type=ValidationErrorType.BRANCH_CODE_MISMATCH,
                        message=f"支店名「{ocr_branch_name}」と店番号「{ocr_branch_code}」が一致しません",
                    ))

        # 店番号フィールドにもマスター情報を付与
        if branch_code_field and ocr_branch_code and resolved_bank_code:
            branch_info = await master.get_branch_by_code(
                resolved_bank_code, ocr_branch_code
            )
            if branch_info:
                branch_code_field.master_match = MasterMatchInfo(
                    master_value=branch_info.name,
                    master_code=branch_info.code,
                    match_score=100.0,
                    match_status="ok",
                )
            else:
                branch_code_field.master_match = MasterMatchInfo(
                    match_score=0.0,
                    match_status="ng",
                )
                errors.append(ValidationError(
                    field_name="店番号",
                    error_type=ValidationErrorType.BRANCH_CODE_NOT_FOUND,
                    message=f"店番号「{ocr_branch_code}」はマスターに存在しません（銀行コード: {resolved_bank_code}）",
                ))

        return errors

    def complement_codes(self, fields: list[OcrField]) -> list[OcrField]:
        """
        マスター照合結果に基づき、コードを補完する。
        銀行名から銀行番号、支店名から店番号を自動決定。
        """
        if not ZenginMasterService.is_initialized():
            return fields

        field_map = {f.field_name: f for f in fields}

        # 銀行番号が空欄で、銀行名マスター照合がOKの場合 → 自動補完
        bank_name_field = field_map.get("銀行名")
        bank_code_field = field_map.get("銀行番号")

        if (
            bank_name_field
            and bank_name_field.master_match
            and bank_name_field.master_match.match_status == "ok"
            and bank_name_field.master_match.master_code
        ):
            if bank_code_field and not bank_code_field.value:
                bank_code_field.corrected_value = bank_name_field.master_match.master_code
                logger.info(
                    f"銀行番号を自動補完: {bank_name_field.master_match.master_code}"
                )

        # 店番号が空欄で、支店名マスター照合がOKの場合 → 自動補完
        branch_name_field = field_map.get("支店名")
        branch_code_field = field_map.get("店番号")

        if (
            branch_name_field
            and branch_name_field.master_match
            and branch_name_field.master_match.match_status == "ok"
            and branch_name_field.master_match.master_code
        ):
            if branch_code_field and not branch_code_field.value:
                branch_code_field.corrected_value = branch_name_field.master_match.master_code
                logger.info(
                    f"店番号を自動補完: {branch_name_field.master_match.master_code}"
                )

        return fields
