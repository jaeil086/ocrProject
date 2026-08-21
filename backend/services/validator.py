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

    def fix_swapped_bank_branch_codes(self, fields: list[OcrField]) -> list[OcrField]:
        """
        銀行番号(4桁)と店番号(3桁)の入れ替わりを桁数で検出し修正する。

        ClaudeのOCRが銀行番号と店番号を取り違えるハルシネーションに対応。
        - 銀行番号は必ず4桁
        - 店番号は必ず3桁
        これに反する場合は入れ替わりを修正する。
        """
        field_map = {f.field_name: f for f in fields}
        bank_code_field = field_map.get("銀行番号")
        branch_code_field = field_map.get("店番号")

        bank_code = bank_code_field.value if bank_code_field else None
        branch_code = branch_code_field.value if branch_code_field else None

        # 両方に値がある場合: 桁数が逆なら入れ替え
        if bank_code and branch_code:
            if len(bank_code) == 3 and len(branch_code) == 4:
                # 入れ替わっている → 修正
                logger.warning(
                    f"銀行番号と店番号の入れ替わりを検出・修正: "
                    f"銀行番号={bank_code}(3桁)→{branch_code}, 店番号={branch_code}(4桁)→{bank_code}"
                )
                bank_code_field.value = branch_code
                branch_code_field.value = bank_code

        # 片方だけに値がある場合: 桁数が正しくなければ入れ替え
        elif bank_code and not branch_code:
            if len(bank_code) == 3:
                # 3桁の値が銀行番号に入っている → 店番号のはず
                logger.warning(
                    f"銀行番号に3桁の値を検出（店番号の誤配置）: {bank_code} → 店番号に移動"
                )
                branch_code_field.value = bank_code
                bank_code_field.value = None
        elif branch_code and not bank_code:
            if len(branch_code) == 4:
                # 4桁の値が店番号に入っている → 銀行番号のはず
                logger.warning(
                    f"店番号に4桁の値を検出（銀行番号の誤配置）: {branch_code} → 銀行番号に移動"
                )
                bank_code_field.value = branch_code
                branch_code_field.value = None

        return fields

    def fix_yucho_codes(self, fields: list[OcrField]) -> list[OcrField]:
        """
        ゆうちょ記号(5桁)と番号(最大8桁)の抽出ミスを検出し修正する。

        ClaudeのOCRが記号と番号の区切り位置を間違えるケースに対応。
        - ゆうちょ記号は必ず5桁
        - ゆうちょ番号は最大8桁
        記号が5桁でない場合、番号と結合して再分割を試みる。
        """
        field_map = {f.field_name: f for f in fields}
        kigo_field = field_map.get("ゆうちょ記号")
        bango_field = field_map.get("ゆうちょ番号")

        kigo = kigo_field.value if kigo_field else None
        bango = bango_field.value if bango_field else None

        # 両方に値がある場合: 記号が5桁でなければ結合して再分割
        if kigo and bango:
            if len(kigo) != 5:
                # 結合して先頭5桁=記号、残り=番号に再分割
                combined = kigo + bango
                if len(combined) >= 5:
                    new_kigo = combined[:5]
                    new_bango = combined[5:] if len(combined) > 5 else None
                    logger.warning(
                        f"ゆうちょ記号/番号の区切りを修正: "
                        f"記号={kigo}+番号={bango} → 記号={new_kigo}, 番号={new_bango}"
                    )
                    kigo_field.value = new_kigo
                    bango_field.value = new_bango if new_bango else None

        # 記号だけに値がある場合: 5桁を超えていたら番号部分を分離
        elif kigo and not bango:
            if len(kigo) > 5:
                new_kigo = kigo[:5]
                new_bango = kigo[5:]
                logger.warning(
                    f"ゆうちょ記号が5桁超（番号が混入）: {kigo} → 記号={new_kigo}, 番号={new_bango}"
                )
                kigo_field.value = new_kigo
                bango_field.value = new_bango

        return fields

    async def check_financial_codes(
        self, fields: list[OcrField]
    ) -> list[ValidationError]:
        """
        金融機関マスターとの照合・交差検証を実行し、
        各フィールドに master_match 情報を付与する。

        検証対象: 銀行名、銀行番号、支店名、店番号
        交差検証: 銀行名↔銀行番号、支店名↔店番号

        交差検証でmismatchの場合:
          - 銀行番号/店番号: マスター値でcorrected_valueを設定、confidence_levelをLOWに
          - 銀行名/支店名: confidence_levelをLOWに変更

        Returns:
            ValidationErrorリスト（交差検証不一致の場合に追加）
        """
        from backend.models.enums import ConfidenceLevel

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

            # 銀行名マッチがOK（95%以上）の場合のみ、名前マッチからコードを確定
            if bank_match.master_code and bank_match.match_status == "ok":
                resolved_bank_code = bank_match.master_code

            # マスター照合結果がng/needs_reviewの場合、confidence_levelをLOWに
            if bank_match.match_status in ("ng", "needs_review"):
                bank_name_field.confidence_level = ConfidenceLevel.LOW

        # 銀行名マッチで確定できなかった場合、OCR銀行番号からの逆引きを試みる
        if not resolved_bank_code and ocr_bank_code:
            code_bank_info = master.get_bank_by_code(ocr_bank_code)
            if code_bank_info:
                resolved_bank_code = ocr_bank_code
                logger.info(
                    f"銀行名マッチで確定できず、OCR銀行番号{ocr_bank_code}から逆引き: {code_bank_info.name}"
                )

        if ocr_bank_name:
            # 銀行名↔銀行番号 交差検証
            if ocr_bank_code and resolved_bank_code:
                if ocr_bank_code == resolved_bank_code:
                    # 一致: OCR銀行番号とマスター確定コードが同じ
                    cross_status = "ok"
                else:
                    # 不一致: OCR銀行番号がマスター確定コードと異なる
                    cross_status = "mismatch"

                bank_name_field.master_match.cross_check_status = cross_status

                if cross_status == "mismatch":
                    errors.append(ValidationError(
                        field_name="銀行番号",
                        error_type=ValidationErrorType.BANK_CODE_MISMATCH,
                        message=f"銀行名「{ocr_bank_name}」と銀行番号「{ocr_bank_code}」が一致しません（正しくは{resolved_bank_code}）",
                    ))
                    # 銀行名フィールドのconfidence_levelをLOWに
                    bank_name_field.confidence_level = ConfidenceLevel.LOW
                    logger.info(
                        f"銀行番号交差検証不一致: OCR={ocr_bank_code}, マスター={resolved_bank_code}"
                    )

            # パターン3対応: 銀行名マッチングがOKでない場合
            # resolved_bank_code（名前マッチから確定）とOCR銀行番号の両方で逆引きして候補に追加
            if (
                bank_name_field.master_match
                and bank_name_field.master_match.match_status != "ok"
            ):
                from backend.models.schemas import MasterMatchCandidate

                # OCR銀行番号から逆引き（ユーザーが実際に書いた番号を優先）
                if ocr_bank_code:
                    code_bank_info = master.get_bank_by_code(ocr_bank_code)
                    if code_bank_info:
                        code_candidate = MasterMatchCandidate(
                            name=f"{code_bank_info.name}（番号{ocr_bank_code}より）",
                            code=code_bank_info.code,
                            score=0.0,
                        )
                        existing_codes = {c.code for c in bank_name_field.master_match.candidates}
                        if code_bank_info.code not in existing_codes:
                            bank_name_field.master_match.candidates.insert(0, code_candidate)

                # resolved_bank_code（名前マッチから確定したコード）からも逆引き
                if resolved_bank_code and resolved_bank_code != ocr_bank_code:
                    code_bank_info = master.get_bank_by_code(resolved_bank_code)
                    if code_bank_info:
                        code_candidate = MasterMatchCandidate(
                            name=f"{code_bank_info.name}（コード{resolved_bank_code}より）",
                            code=code_bank_info.code,
                            score=0.0,
                        )
                        existing_codes = {c.code for c in bank_name_field.master_match.candidates}
                        if code_bank_info.code not in existing_codes:
                            bank_name_field.master_match.candidates.insert(0, code_candidate)

                # 候補数を5件に制限
                bank_name_field.master_match.candidates = bank_name_field.master_match.candidates[:5]

        # 銀行番号フィールドにマスター情報を付与
        # ※ OCR銀行番号が空欄の場合はマスター照合を行わない（空欄に推測値を入れない）
        if bank_code_field and ocr_bank_code:
            if resolved_bank_code:
                # マスターで銀行コードが確定している場合
                bank_info = master.get_bank_by_code(resolved_bank_code)
                if ocr_bank_code == resolved_bank_code:
                    # OCR値とマスター値が一致 → OK
                    bank_code_field.master_match = MasterMatchInfo(
                        master_value=bank_info.name if bank_info else None,
                        master_code=resolved_bank_code,
                        match_score=100.0,
                        match_status="ok",
                    )
                else:
                    # OCR値とマスター値が不一致 → 候補として提示（OCR値は変更しない）
                    # OCR銀行番号から逆引きした候補も追加
                    code_candidates = []
                    from backend.models.schemas import MasterMatchCandidate
                    ocr_code_bank = master.get_bank_by_code(ocr_bank_code)
                    if ocr_code_bank:
                        code_candidates.append(MasterMatchCandidate(
                            name=f"{ocr_code_bank.name}（番号{ocr_bank_code}より）",
                            code=ocr_code_bank.code,
                            score=0.0,
                        ))

                    bank_code_field.master_match = MasterMatchInfo(
                        master_value=bank_info.name if bank_info else None,
                        master_code=resolved_bank_code,
                        match_score=0.0,  # OCR値とは不一致なので0%
                        match_status="needs_review",
                        cross_check_status="mismatch",
                        candidates=code_candidates,
                    )
                    bank_code_field.confidence_level = ConfidenceLevel.LOW
                    logger.info(
                        f"銀行番号不一致（候補提示）: OCR={ocr_bank_code}, マスター候補={resolved_bank_code}"
                    )
            else:
                # 銀行名からコード確定できなかった場合、OCR銀行番号をマスターで検証
                bank_info = master.get_bank_by_code(ocr_bank_code)
                if bank_info:
                    bank_code_field.master_match = MasterMatchInfo(
                        master_value=bank_info.name,
                        master_code=bank_info.code,
                        match_score=100.0,
                        match_status="ok",
                    )
                    resolved_bank_code = ocr_bank_code
                else:
                    bank_code_field.master_match = MasterMatchInfo(
                        match_score=0.0,
                        match_status="ng",
                    )
                    bank_code_field.confidence_level = ConfidenceLevel.LOW
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

        resolved_branch_code: Optional[str] = None  # マスターで確定した支店コード

        if ocr_branch_name and resolved_bank_code:
            # 支店名をマスターと照合
            branch_match = await master.match_branch(
                resolved_bank_code, ocr_branch_name
            )
            branch_name_field.master_match = branch_match

            # 支店名マッチがOK（95%以上）の場合のみ、名前マッチからコードを確定
            if branch_match.master_code and branch_match.match_status == "ok":
                resolved_branch_code = branch_match.master_code

            # マスター照合結果がng/needs_reviewの場合、confidence_levelをLOWに
            if branch_match.match_status in ("ng", "needs_review"):
                branch_name_field.confidence_level = ConfidenceLevel.LOW

        # 支店名マッチで確定できなかった場合、OCR店番号からの逆引きを試みる
        if not resolved_branch_code and ocr_branch_code and resolved_bank_code:
            code_branch_info = await master.get_branch_by_code(
                resolved_bank_code, ocr_branch_code
            )
            if code_branch_info:
                resolved_branch_code = ocr_branch_code
                logger.info(
                    f"支店名マッチで確定できず、OCR店番号{ocr_branch_code}から逆引き: {code_branch_info.name}"
                )

        if ocr_branch_name and resolved_bank_code:
            # 支店名↔店番号 交差検証
            if ocr_branch_code and resolved_branch_code:
                if ocr_branch_code == resolved_branch_code:
                    cross_status = "ok"
                else:
                    cross_status = "mismatch"

                branch_name_field.master_match.cross_check_status = cross_status

                if cross_status == "mismatch":
                    errors.append(ValidationError(
                        field_name="店番号",
                        error_type=ValidationErrorType.BRANCH_CODE_MISMATCH,
                        message=f"支店名「{ocr_branch_name}」と店番号「{ocr_branch_code}」が一致しません（正しくは{resolved_branch_code}）",
                    ))
                    # 支店名フィールドのconfidence_levelをLOWに
                    branch_name_field.confidence_level = ConfidenceLevel.LOW
                    logger.info(
                        f"店番号交差検証不一致: OCR={ocr_branch_code}, マスター={resolved_branch_code}"
                    )

            # パターン3対応: 支店名マッチングがOKでない場合
            # OCR店番号から逆引きした候補も追加する
            # resolved_bank_codeとOCR銀行番号の両方で支店を検索
            if (
                branch_name_field.master_match
                and branch_name_field.master_match.match_status != "ok"
                and ocr_branch_code
            ):
                from backend.models.schemas import MasterMatchCandidate

                # まずresolved_bank_code(銀行名マッチから)で検索
                code_branch_info = None
                if resolved_bank_code:
                    code_branch_info = await master.get_branch_by_code(
                        resolved_bank_code, ocr_branch_code
                    )

                # 見つからなければOCR銀行番号で検索
                if not code_branch_info and ocr_bank_code and ocr_bank_code != resolved_bank_code:
                    code_branch_info = await master.get_branch_by_code(
                        ocr_bank_code, ocr_branch_code
                    )

                if code_branch_info:
                    # OCR店番号に対応するマスター支店を候補の先頭に追加
                    code_candidate = MasterMatchCandidate(
                        name=f"{code_branch_info.name}（番号{ocr_branch_code}より）",
                        code=code_branch_info.code,
                        score=0.0,  # 名前マッチではないため0%
                    )
                    existing_codes = {c.code for c in branch_name_field.master_match.candidates}
                    if code_branch_info.code not in existing_codes:
                        branch_name_field.master_match.candidates.insert(0, code_candidate)
                # 候補数を5件に制限
                branch_name_field.master_match.candidates = branch_name_field.master_match.candidates[:5]

        # 店番号フィールドにマスター情報を付与
        # ※ OCR店番号が空欄の場合はマスター照合を行わない（空欄に推測値を入れない）
        if branch_code_field and ocr_branch_code and resolved_bank_code:
            if resolved_branch_code:
                # マスターで支店コードが確定している場合
                branch_info = await master.get_branch_by_code(
                    resolved_bank_code, resolved_branch_code
                )
                if ocr_branch_code == resolved_branch_code:
                    # OCR値とマスター値が一致 → OK
                    branch_code_field.master_match = MasterMatchInfo(
                        master_value=branch_info.name if branch_info else None,
                        master_code=resolved_branch_code,
                        match_score=100.0,
                        match_status="ok",
                    )
                else:
                    # OCR値とマスター値が不一致 → 候補として提示（OCR値は変更しない）
                    # OCR店番号から逆引きした候補も追加
                    code_candidates = []
                    if ocr_branch_code:
                        from backend.models.schemas import MasterMatchCandidate
                        # resolved_bank_codeで検索
                        ocr_code_branch = await master.get_branch_by_code(
                            resolved_bank_code, ocr_branch_code
                        )
                        # 見つからなければOCR銀行番号で検索
                        if not ocr_code_branch and ocr_bank_code and ocr_bank_code != resolved_bank_code:
                            ocr_code_branch = await master.get_branch_by_code(
                                ocr_bank_code, ocr_branch_code
                            )
                        if ocr_code_branch:
                            code_candidates.append(MasterMatchCandidate(
                                name=f"{ocr_code_branch.name}（番号{ocr_branch_code}より）",
                                code=ocr_code_branch.code,
                                score=0.0,
                            ))

                    branch_code_field.master_match = MasterMatchInfo(
                        master_value=branch_info.name if branch_info else None,
                        master_code=resolved_branch_code,
                        match_score=0.0,  # OCR値とは不一致なので0%
                        match_status="needs_review",
                        cross_check_status="mismatch",
                        candidates=code_candidates,
                    )
                    branch_code_field.confidence_level = ConfidenceLevel.LOW
                    logger.info(
                        f"店番号不一致（候補提示）: OCR={ocr_branch_code}, マスター候補={resolved_branch_code}"
                    )
            else:
                # 支店名からコード確定できなかった場合、OCR店番号をマスターで検証
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
                    branch_code_field.confidence_level = ConfidenceLevel.LOW
                    errors.append(ValidationError(
                        field_name="店番号",
                        error_type=ValidationErrorType.BRANCH_CODE_NOT_FOUND,
                        message=f"店番号「{ocr_branch_code}」はマスターに存在しません（銀行コード: {resolved_bank_code}）",
                    ))

        return errors


