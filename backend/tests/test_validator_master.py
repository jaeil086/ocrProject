"""
バリデーションエンジン（金融機関マスター検証）のテスト

Validator.check_financial_codes()のマスター照合・交差検証ロジックを検証する。
"""

import pytest

from backend.models.enums import ConfidenceLevel, FormType, ValidationErrorType
from backend.models.schemas import OcrField, ValidationError
from backend.services.validator import Validator
from backend.services.zengin_master import BankInfo, BranchInfo, ZenginMasterService


def _make_field(name: str, value: str = None) -> OcrField:
    """テスト用OcrFieldヘルパー"""
    return OcrField(
        field_name=name,
        value=value,
        confidence_score=90.0,
        confidence_level=ConfidenceLevel.HIGH,
        is_confirmed=False,
        corrected_value=None,
    )


@pytest.fixture
def master_service():
    """テスト用にマスターサービスを手動初期化"""
    service = ZenginMasterService()
    service._banks = {
        "0001": BankInfo(code="0001", name="みずほ銀行", kana="ミズホ", hira="みずほ", roma="mizuho"),
        "0005": BankInfo(code="0005", name="三菱UFJ銀行", kana="ミツビシ", hira="みつびし", roma="mitsubishi"),
        "0138": BankInfo(code="0138", name="横浜銀行", kana="ヨコハマ", hira="よこはま", roma="yokohama"),
        "0137": BankInfo(code="0137", name="きらぼし銀行", kana="キラボシ", hira="きらぼし", roma="kiraboshi"),
    }
    service._bank_name_index = {bank.name: bank.code for bank in service._banks.values()}
    service._branches_cache = {
        "0138": {
            "931": BranchInfo(code="931", name="町田支店", kana="マチダ", hira="まちだ", roma="machida"),
            "210": BranchInfo(code="210", name="横浜駅前支店", kana="ヨコハマエキマエ", hira="よこはまえきまえ", roma="yokohamaekimae"),
        }
    }
    service._initialized = True
    ZenginMasterService._instance = service
    return service


@pytest.fixture
def validator():
    """テスト用バリデーター"""
    return Validator()


# === check_financial_codes テスト ===


class TestCheckFinancialCodes:
    """check_financial_codes()のテスト"""

    @pytest.mark.asyncio
    async def test_bank_name_match_ok(self, validator, master_service):
        """銀行名がマスターと一致する場合"""
        fields = [
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("銀行番号", "0138"),
            _make_field("支店名", "町田"),
            _make_field("店番号", "931"),
        ]

        errors = await validator.check_financial_codes(fields)

        # エラーなし
        assert len(errors) == 0

        # 銀行名フィールドにmaster_matchが付与されている
        bank_field = next(f for f in fields if f.field_name == "銀行名")
        assert bank_field.master_match is not None
        assert bank_field.master_match.match_status == "ok"
        assert bank_field.master_match.master_code == "0138"

    @pytest.mark.asyncio
    async def test_bank_code_mismatch(self, validator, master_service):
        """銀行名と銀行番号が不一致の場合"""
        fields = [
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("銀行番号", "0005"),  # 三菱UFJのコード
            _make_field("支店名"),
            _make_field("店番号"),
        ]

        errors = await validator.check_financial_codes(fields)

        # 交差検証エラーが発生
        bank_code_errors = [e for e in errors if e.field_name == "銀行番号"]
        assert len(bank_code_errors) > 0

        # 銀行名のcross_check_statusがmismatch
        bank_field = next(f for f in fields if f.field_name == "銀行名")
        assert bank_field.master_match.cross_check_status == "mismatch"

    @pytest.mark.asyncio
    async def test_branch_code_mismatch(self, validator, master_service):
        """支店名と店番号が不一致の場合"""
        fields = [
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("銀行番号", "0138"),
            _make_field("支店名", "町田"),
            _make_field("店番号", "210"),  # 横浜駅前支店のコード
        ]

        errors = await validator.check_financial_codes(fields)

        # 店番号の交差検証エラー
        branch_code_errors = [e for e in errors if e.field_name == "店番号"
                              and e.error_type == ValidationErrorType.BRANCH_CODE_MISMATCH]
        assert len(branch_code_errors) > 0

    @pytest.mark.asyncio
    async def test_bank_code_not_found(self, validator, master_service):
        """銀行番号がマスターに存在しない場合 → 銀行名からコード確定しているためMISMATCHになる"""
        fields = [
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("銀行番号", "9999"),  # 存在しないコード
            _make_field("支店名"),
            _make_field("店番号"),
        ]

        errors = await validator.check_financial_codes(fields)

        # 銀行名マスター照合でコード確定(0138)のため、9999との不一致エラー
        mismatch_errors = [e for e in errors if e.error_type == ValidationErrorType.BANK_CODE_MISMATCH]
        assert len(mismatch_errors) > 0

        # 銀行番号フィールドはOCR値を変更しない（corrected_valueは設定しない）
        bank_code_field = next(f for f in fields if f.field_name == "銀行番号")
        assert bank_code_field.corrected_value is None
        # confidence_levelはLOWに変更される
        assert bank_code_field.confidence_level == ConfidenceLevel.LOW
        # master_matchに候補情報（マスター確定コード）が入っている
        assert bank_code_field.master_match is not None
        assert bank_code_field.master_match.master_code == "0138"
        assert bank_code_field.master_match.cross_check_status == "mismatch"

    @pytest.mark.asyncio
    async def test_yucho_skip(self, validator, master_service):
        """ゆうちょ利用時は銀行マスター検証スキップ"""
        fields = [
            _make_field("銀行名"),
            _make_field("銀行番号"),
            _make_field("支店名"),
            _make_field("店番号"),
            _make_field("ゆうちょ記号", "11137"),
            _make_field("ゆうちょ番号", "12345671"),
        ]

        errors = await validator.check_financial_codes(fields)

        # エラーなし（スキップ）
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_no_master_service(self, validator):
        """マスターサービス未初期化の場合"""
        # シングルトンをリセット
        ZenginMasterService._instance = None

        fields = [
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("銀行番号", "0138"),
        ]

        errors = await validator.check_financial_codes(fields)

        # エラーなし（スキップ）
        assert len(errors) == 0


# === check_missing_fields テスト（既存機能の回帰テスト） ===


class TestCheckMissingFields:
    """check_missing_fields()の回帰テスト"""

    def test_all_fields_present(self, validator):
        """全フィールド揃っている場合はエラーなし"""
        fields = [
            _make_field("預金者氏名", "山田太郎"),
            _make_field("預金者フリガナ", "ヤマダタロウ"),
            _make_field("お届出印金融機関", "あり"),
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("支店名", "町田"),
            _make_field("預金種目", "普通"),
            _make_field("口座番号", "1234567"),
            _make_field("銀行番号", "0138"),
            _make_field("店番号", "931"),
            _make_field("契約者番号", "10008"),
        ]

        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        assert len(errors) == 0

    def test_missing_bank_code_error(self, validator):
        """銀行番号が空の場合にエラー"""
        fields = [
            _make_field("預金者氏名", "山田太郎"),
            _make_field("預金者フリガナ", "ヤマダタロウ"),
            _make_field("お届出印金融機関", "あり"),
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("支店名", "町田"),
            _make_field("預金種目", "普通"),
            _make_field("口座番号", "1234567"),
            _make_field("銀行番号"),  # 空
            _make_field("店番号", "931"),
            _make_field("契約者番号", "10008"),
        ]

        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        missing_errors = [e for e in errors if e.field_name == "銀行番号"]
        assert len(missing_errors) == 1

    def test_yucho_fields_not_required_when_bank_used(self, validator):
        """銀行利用時はゆうちょフィールドは必須としない"""
        fields = [
            _make_field("預金者氏名", "山田太郎"),
            _make_field("預金者フリガナ", "ヤマダタロウ"),
            _make_field("お届出印金融機関", "あり"),
            _make_field("銀行名", "横浜（銀行）"),
            _make_field("支店名", "町田"),
            _make_field("預金種目", "普通"),
            _make_field("口座番号", "1234567"),
            _make_field("銀行番号", "0138"),
            _make_field("店番号", "931"),
            _make_field("ゆうちょ記号"),  # 空
            _make_field("ゆうちょ番号"),  # 空
            _make_field("契約者番号", "10008"),
        ]

        errors = validator.check_missing_fields(fields, FormType.GENERAL)
        yucho_errors = [e for e in errors if "ゆうちょ" in e.field_name]
        assert len(yucho_errors) == 0
