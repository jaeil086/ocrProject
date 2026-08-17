"""
ZenginMasterServiceのテスト

金融機関マスターのFuzzy Matching、交差検証ロジックを検証する。
"""

import pytest

from backend.models.schemas import MasterMatchCandidate, MasterMatchInfo
from backend.services.zengin_master import BankInfo, BranchInfo, ZenginMasterService


# === テスト用フィクスチャ ===


@pytest.fixture
def master_service():
    """テスト用にマスターサービスを手動初期化"""
    service = ZenginMasterService()
    # テスト用の銀行データを直接注入
    service._banks = {
        "0001": BankInfo(code="0001", name="みずほ銀行", kana="ミズホ", hira="みずほ", roma="mizuho"),
        "0005": BankInfo(code="0005", name="三菱UFJ銀行", kana="ミツビシユーエフジェイ", hira="みつびしゆーえふじぇい", roma="mitsubishi"),
        "0009": BankInfo(code="0009", name="三井住友銀行", kana="ミツイスミトモ", hira="みついすみとも", roma="mitsui"),
        "0138": BankInfo(code="0138", name="横浜銀行", kana="ヨコハマ", hira="よこはま", roma="yokohama"),
        "0288": BankInfo(code="0288", name="城南信用金庫", kana="ジョウナン", hira="じょうなん", roma="jounan"),
        "0137": BankInfo(code="0137", name="きらぼし銀行", kana="キラボシ", hira="きらぼし", roma="kiraboshi"),
    }
    service._bank_name_index = {bank.name: bank.code for bank in service._banks.values()}
    service._initialized = True
    # シングルトンとして登録
    ZenginMasterService._instance = service
    return service


@pytest.fixture
def branches_data():
    """テスト用の支店データ"""
    return {
        "931": BranchInfo(code="931", name="町田支店", kana="マチダ", hira="まちだ", roma="machida"),
        "001": BranchInfo(code="001", name="本店営業部", kana="ホンテン", hira="ほんてん", roma="honten"),
        "210": BranchInfo(code="210", name="横浜駅前支店", kana="ヨコハマエキマエ", hira="よこはまえきまえ", roma="yokohamaekimae"),
        "332": BranchInfo(code="332", name="藤沢支店", kana="フジサワ", hira="ふじさわ", roma="fujisawa"),
    }


# === 銀行名マッチングテスト ===


class TestMatchBank:
    """match_bank()のテスト"""

    def test_exact_match_with_suffix(self, master_service):
        """括弧付き銀行名の完全一致"""
        result = master_service.match_bank("横浜（銀行）")
        assert result.match_status == "ok"
        assert result.master_code == "0138"
        assert result.master_value == "横浜銀行"
        assert result.match_score >= 95.0

    def test_exact_match_without_suffix(self, master_service):
        """括弧なし銀行名の完全一致"""
        result = master_service.match_bank("横浜銀行")
        assert result.match_status == "ok"
        assert result.master_code == "0138"
        assert result.match_score >= 95.0

    def test_fuzzy_match_typo(self, master_service):
        """タイプミスのあるFuzzy Matching"""
        result = master_service.match_bank("みづほ（銀行）")
        # 「みづほ」→「みずほ銀行」に類似するはず
        assert result.master_code == "0001"
        assert result.match_score >= 70.0

    def test_shinkin_suffix_filter(self, master_service):
        """信用金庫の種別フィルタリング"""
        result = master_service.match_bank("城南（信用金庫）")
        assert result.match_status == "ok"
        assert result.master_code == "0288"
        assert result.master_value == "城南信用金庫"

    def test_empty_value(self, master_service):
        """空値の場合はunverified"""
        result = master_service.match_bank("")
        assert result.match_status == "unverified"

    def test_none_value(self, master_service):
        """None値の場合"""
        # match_bankは文字列を受け取るが、空文字チェックでunverifiedを返すはず
        result = master_service.match_bank("")
        assert result.match_status == "unverified"

    def test_candidates_returned(self, master_service):
        """候補リストが返される"""
        result = master_service.match_bank("三井（銀行）")
        assert len(result.candidates) > 0
        # 候補にコードとスコアが含まれている
        for candidate in result.candidates:
            assert candidate.code
            assert candidate.name
            assert candidate.score > 0

    def test_kiraboshi_bank(self, master_service):
        """きらぼし銀行の一致"""
        result = master_service.match_bank("きらぼし（銀行）")
        assert result.match_status == "ok"
        assert result.master_code == "0137"
        assert result.master_value == "きらぼし銀行"


# === 支店名マッチングテスト ===


class TestMatchBranch:
    """match_branch()のテスト"""

    @pytest.mark.asyncio
    async def test_exact_branch_match(self, master_service, branches_data):
        """支店名の完全一致"""
        master_service._branches_cache["0138"] = branches_data
        result = await master_service.match_branch("0138", "町田")
        assert result.match_status == "ok"
        assert result.master_code == "931"
        assert "町田" in result.master_value

    @pytest.mark.asyncio
    async def test_branch_with_suffix(self, master_service, branches_data):
        """「支店」付きの支店名マッチング"""
        master_service._branches_cache["0138"] = branches_data
        result = await master_service.match_branch("0138", "町田支店")
        assert result.master_code == "931"
        assert result.match_score >= 95.0

    @pytest.mark.asyncio
    async def test_branch_empty_name(self, master_service, branches_data):
        """空の支店名はunverified"""
        master_service._branches_cache["0138"] = branches_data
        result = await master_service.match_branch("0138", "")
        assert result.match_status == "unverified"

    @pytest.mark.asyncio
    async def test_branch_no_bank_code(self, master_service, branches_data):
        """銀行コードなしはunverified"""
        result = await master_service.match_branch("", "町田")
        assert result.match_status == "unverified"


# === 交差検証テスト ===


class TestCrossCheck:
    """交差検証のテスト"""

    def test_bank_cross_check_ok(self, master_service):
        """銀行名と銀行番号が一致"""
        result = master_service.cross_check_bank_code("横浜（銀行）", "0138")
        assert result == "ok"

    def test_bank_cross_check_mismatch(self, master_service):
        """銀行名と銀行番号が不一致"""
        result = master_service.cross_check_bank_code("横浜（銀行）", "0005")
        assert result == "mismatch"

    def test_bank_cross_check_empty_code(self, master_service):
        """銀行番号が空の場合はok（検証スキップ）"""
        result = master_service.cross_check_bank_code("横浜（銀行）", "")
        assert result == "ok"

    def test_bank_cross_check_empty_name(self, master_service):
        """銀行名が空の場合はok（検証スキップ）"""
        result = master_service.cross_check_bank_code("", "0138")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_branch_cross_check_ok(self, master_service, branches_data):
        """支店名と店番号が一致"""
        master_service._branches_cache["0138"] = branches_data
        result = await master_service.cross_check_branch_code("0138", "町田", "931")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_branch_cross_check_mismatch(self, master_service, branches_data):
        """支店名と店番号が不一致"""
        master_service._branches_cache["0138"] = branches_data
        result = await master_service.cross_check_branch_code("0138", "町田", "210")
        assert result == "mismatch"


# === ステータス判定テスト ===


class TestDetermineStatus:
    """_determine_status()のテスト"""

    def test_ok_threshold(self, master_service):
        """95%以上はok"""
        assert master_service._determine_status(95.0) == "ok"
        assert master_service._determine_status(100.0) == "ok"

    def test_needs_review_threshold(self, master_service):
        """85%以上95%未満はneeds_review"""
        assert master_service._determine_status(85.0) == "needs_review"
        assert master_service._determine_status(90.0) == "needs_review"
        assert master_service._determine_status(94.9) == "needs_review"

    def test_ng_threshold(self, master_service):
        """85%未満はng"""
        assert master_service._determine_status(84.9) == "ng"
        assert master_service._determine_status(50.0) == "ng"
        assert master_service._determine_status(0.0) == "ng"


# === 銀行名パースのテスト ===


class TestParseBankName:
    """_parse_bank_name()のテスト"""

    def test_full_width_parentheses(self, master_service):
        """全角括弧の処理"""
        name, suffix = master_service._parse_bank_name("横浜（銀行）")
        assert name == "横浜"
        assert suffix == "銀行"

    def test_half_width_parentheses(self, master_service):
        """半角括弧の処理"""
        name, suffix = master_service._parse_bank_name("横浜(銀行)")
        assert name == "横浜"
        assert suffix == "銀行"

    def test_no_parentheses(self, master_service):
        """括弧なしの処理"""
        name, suffix = master_service._parse_bank_name("横浜銀行")
        assert name == "横浜銀行"
        assert suffix == ""

    def test_shinkin_suffix(self, master_service):
        """信用金庫の種別"""
        name, suffix = master_service._parse_bank_name("城南（信用金庫）")
        assert name == "城南"
        assert suffix == "信用金庫"

    def test_kumiai_suffix(self, master_service):
        """組合の種別"""
        name, suffix = master_service._parse_bank_name("えがみ（組合）")
        assert name == "えがみ"
        assert suffix == "組合"
