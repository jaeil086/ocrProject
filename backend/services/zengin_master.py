"""
全銀金融機関マスターサービス

Zengin Code APIからマスターデータを取得・キャッシュし、
OCR抽出値との照合（Fuzzy Matching）・交差検証を行う。

設計方針:
  - banks.json は FastAPI起動時にロード（起動時ロード）
  - branches/{bank_code}.json は必要時にロード（Lazy Loading）
  - ファイルキャッシュ＋メモリキャッシュの2層構造
  - ダウンロード失敗時はキャッシュファイルをフォールバック使用
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from rapidfuzz import fuzz, process

from backend.config import (
    MASTER_MATCH_OK_THRESHOLD,
    MASTER_MATCH_REVIEW_THRESHOLD,
    ZENGIN_BANKS_CACHE_FILE,
    ZENGIN_BANKS_URL,
    ZENGIN_BRANCHES_CACHE_DIR,
    ZENGIN_BRANCHES_URL_TEMPLATE,
    ZENGIN_CACHE_DIR,
    ZENGIN_CACHE_TTL_SECONDS,
)
from backend.models.schemas import MasterMatchCandidate, MasterMatchInfo

logger = logging.getLogger(__name__)


# === データ構造 ===

class BankInfo:
    """銀行情報"""
    __slots__ = ("code", "name", "kana", "hira", "roma")

    def __init__(self, code: str, name: str, kana: str, hira: str, roma: str):
        self.code = code
        self.name = name
        self.kana = kana
        self.hira = hira
        self.roma = roma


class BranchInfo:
    """支店情報"""
    __slots__ = ("code", "name", "kana", "hira", "roma")

    def __init__(self, code: str, name: str, kana: str, hira: str, roma: str):
        self.code = code
        self.name = name
        self.kana = kana
        self.hira = hira
        self.roma = roma


# === マスターサービス ===

class ZenginMasterService:
    """
    全銀金融機関マスターサービス（シングルトン）

    使用パターン:
        # 起動時
        await ZenginMasterService.initialize()

        # OCRパイプラインから呼び出し
        service = ZenginMasterService.get_instance()
        result = service.match_bank("横浜（銀行）")
    """

    _instance: Optional["ZenginMasterService"] = None

    def __init__(self):
        # 銀行マスター: {bank_code: BankInfo}
        self._banks: dict[str, BankInfo] = {}
        # 銀行名→コード逆引きインデックス
        self._bank_name_index: dict[str, str] = {}
        # 支店マスターメモリキャッシュ: {bank_code: {branch_code: BranchInfo}}
        self._branches_cache: dict[str, dict[str, BranchInfo]] = {}
        # 初期化済みフラグ
        self._initialized: bool = False

    @classmethod
    async def initialize(cls) -> "ZenginMasterService":
        """
        FastAPI起動時に呼び出し。
        banks.jsonをロードしてシングルトンインスタンスを初期化する。
        """
        instance = cls()
        await instance._load_banks()
        instance._initialized = True
        cls._instance = instance
        logger.info(
            f"ZenginMasterService初期化完了: 銀行数={len(instance._banks)}"
        )
        return instance

    @classmethod
    def get_instance(cls) -> "ZenginMasterService":
        """シングルトンインスタンスを取得"""
        if cls._instance is None:
            raise RuntimeError(
                "ZenginMasterService未初期化。先にinitialize()を呼んでください。"
            )
        return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        """初期化済みかどうか"""
        return cls._instance is not None and cls._instance._initialized

    # === 公開API ===

    def match_bank(self, ocr_bank_name: str) -> MasterMatchInfo:
        """
        OCR抽出の銀行名をマスターと照合する。

        Args:
            ocr_bank_name: OCR値（例: "横浜（銀行）"、"みづほ"）

        Returns:
            MasterMatchInfo: マッチング結果
        """
        if not ocr_bank_name:
            return MasterMatchInfo(match_status="unverified")

        # 銀行名から種別括弧を除去して純粋な名前を取得
        clean_name, suffix = self._parse_bank_name(ocr_bank_name)

        if not clean_name:
            return MasterMatchInfo(match_status="unverified")

        # マスター候補リスト構築（種別フィルタリング付き）
        candidates = self._get_bank_candidates(clean_name, suffix)

        if not candidates:
            return MasterMatchInfo(
                match_score=0.0,
                match_status="ng",
                candidates=[],
            )

        # 最良候補
        best = candidates[0]
        status = self._determine_status(best.score)

        return MasterMatchInfo(
            master_value=best.name,
            master_code=best.code,
            match_score=best.score,
            match_status=status,
            candidates=candidates[:3],  # 上位3件
        )

    async def match_branch(
        self, bank_code: str, ocr_branch_name: str
    ) -> MasterMatchInfo:
        """
        OCR抽出の支店名をマスターと照合する。

        Args:
            bank_code: 確定済み銀行コード（4桁）
            ocr_branch_name: OCR値（例: "町田"）

        Returns:
            MasterMatchInfo: マッチング結果
        """
        if not ocr_branch_name or not bank_code:
            return MasterMatchInfo(match_status="unverified")

        # 支店データをLazy Loading
        branches = await self._get_branches(bank_code)

        if not branches:
            return MasterMatchInfo(
                match_score=0.0,
                match_status="ng",
                candidates=[],
            )

        # 支店名マッチング
        candidates = self._fuzzy_match_branches(ocr_branch_name, branches)

        if not candidates:
            return MasterMatchInfo(
                match_score=0.0,
                match_status="ng",
                candidates=[],
            )

        best = candidates[0]
        status = self._determine_status(best.score)

        return MasterMatchInfo(
            master_value=best.name,
            master_code=best.code,
            match_score=best.score,
            match_status=status,
            candidates=candidates[:3],
        )

    def cross_check_bank_code(
        self, ocr_bank_name: str, ocr_bank_code: str
    ) -> str:
        """
        銀行名と銀行番号の交差検証。

        Returns:
            "ok" / "mismatch"
        """
        if not ocr_bank_name or not ocr_bank_code:
            return "ok"  # 片方が空なら検証スキップ

        # 銀行名からマスター照合でコードを取得
        match_result = self.match_bank(ocr_bank_name)

        if match_result.master_code and match_result.match_status == "ok":
            # マスターで確定したコードとOCR抽出コードを比較
            if match_result.master_code == ocr_bank_code:
                return "ok"
            else:
                return "mismatch"

        # マスターで確定できなかった場合、コードから逆引き検証
        if ocr_bank_code in self._banks:
            bank_info = self._banks[ocr_bank_code]
            clean_name, _ = self._parse_bank_name(ocr_bank_name)
            # コードに対応する銀行名とOCR銀行名を比較
            score = fuzz.token_sort_ratio(clean_name, bank_info.name)
            if score >= MASTER_MATCH_REVIEW_THRESHOLD:
                return "ok"
            else:
                return "mismatch"

        return "ok"  # コードがマスターに存在しない場合は検証不可

    async def cross_check_branch_code(
        self, bank_code: str, ocr_branch_name: str, ocr_branch_code: str
    ) -> str:
        """
        支店名と店番号の交差検証。

        Returns:
            "ok" / "mismatch"
        """
        if not ocr_branch_name or not ocr_branch_code or not bank_code:
            return "ok"  # 片方が空なら検証スキップ

        branches = await self._get_branches(bank_code)
        if not branches:
            return "ok"  # 支店データ取得不可なら検証スキップ

        # 支店名からマスター照合
        match_result = await self.match_branch(bank_code, ocr_branch_name)

        if match_result.master_code and match_result.match_status == "ok":
            if match_result.master_code == ocr_branch_code:
                return "ok"
            else:
                return "mismatch"

        # 支店コードから逆引き検証
        if ocr_branch_code in branches:
            branch_info = branches[ocr_branch_code]
            score = fuzz.token_sort_ratio(ocr_branch_name, branch_info.name)
            if score >= MASTER_MATCH_REVIEW_THRESHOLD:
                return "ok"
            else:
                return "mismatch"

        return "ok"


    # 銀行のコード取得
    def get_bank_by_code(self, bank_code: str) -> Optional[BankInfo]:
        """銀行コードから銀行情報を取得"""
        return self._banks.get(bank_code)

    async def get_branch_by_code(
        self, bank_code: str, branch_code: str
    ) -> Optional[BranchInfo]:
        """銀行コード+支店コードから支店情報を取得"""
        branches = await self._get_branches(bank_code)
        if branches:
            return branches.get(branch_code)
        return None

    # === 内部メソッド ===

    def _parse_bank_name(self, ocr_bank_name: str) -> tuple[str, str]:
        """
        OCR銀行名を分解: "横浜（銀行）" → ("横浜", "銀行")

        Returns:
            (純粋な銀行名, 種別サフィックス)
        """
        # 全角/半角括弧に対応
        match = re.match(r"^(.+?)[（(](.+?)[）)]$", ocr_bank_name.strip())
        if match:
            return match.group(1).strip(), match.group(2).strip()

        # 括弧なしの場合はそのまま返す
        return ocr_bank_name.strip(), ""

    def _get_bank_candidates(
        self, clean_name: str, suffix: str
    ) -> list[MasterMatchCandidate]:
        """
        銀行名候補をFuzzy Matchingで検索。
        種別（銀行/信用金庫/組合）で候補を絞り込む。
        """
        # マスターの銀行名リスト（種別フィルタリング付き）
        # 種別→マスター名称のサフィックスマッピング
        suffix_map = {
            "銀行": "銀行",
            "信用金庫": "信用金庫",
            "組合": "信用組合",
        }

        target_suffix = suffix_map.get(suffix, "")
        candidates_dict: dict[str, str] = {}  # {name: code}

        for code, bank in self._banks.items():
            # 種別フィルタ: 種別指定がある場合はそのサフィックスを持つ銀行のみ
            if target_suffix:
                if not bank.name.endswith(target_suffix):
                    continue

            candidates_dict[bank.name] = code

        if not candidates_dict:
            # フィルタで候補が0になった場合は全銀行を対象にする
            candidates_dict = {bank.name: bank.code for bank in self._banks.values()}

        # Fuzzy Matching実行
        # clean_name（括弧内除去済み）に「銀行」等のサフィックスを付加して比較
        search_names = [clean_name]
        if target_suffix:
            search_names.append(clean_name + target_suffix)

        best_results: list[tuple[str, float, str]] = []

        for search_name in search_names:
            results = process.extract(
                search_name,
                list(candidates_dict.keys()),
                scorer=fuzz.token_sort_ratio,
                limit=5,
            )
            for name, score, _ in results:
                best_results.append((name, score, candidates_dict[name]))

        # 重複排除して最良スコア順にソート
        seen: set[str] = set()
        unique_results: list[tuple[str, float, str]] = []
        for name, score, code in sorted(best_results, key=lambda x: -x[1]):
            if code not in seen:
                seen.add(code)
                unique_results.append((name, score, code))

        return [
            MasterMatchCandidate(name=name, code=code, score=score)
            for name, score, code in unique_results[:5]
        ]

    def _fuzzy_match_branches(
        self, ocr_branch_name: str, branches: dict[str, BranchInfo]
    ) -> list[MasterMatchCandidate]:
        """支店名をFuzzy Matchingで検索"""
        branch_names = {info.name: info.code for info in branches.values()}

        # 「支店」「出張所」等のサフィックスを付加して検索
        search_variants = [ocr_branch_name]
        # 既にサフィックスがなければ追加パターンも試す
        if not any(ocr_branch_name.endswith(s) for s in ("支店", "出張所", "営業部")):
            search_variants.append(ocr_branch_name + "支店")

        best_results: list[tuple[str, float, str]] = []

        for search_name in search_variants:
            results = process.extract(
                search_name,
                list(branch_names.keys()),
                scorer=fuzz.token_sort_ratio,
                limit=5,
            )
            for name, score, _ in results:
                best_results.append((name, score, branch_names[name]))

        # 重複排除してスコア順
        seen: set[str] = set()
        unique_results: list[tuple[str, float, str]] = []
        for name, score, code in sorted(best_results, key=lambda x: -x[1]):
            if code not in seen:
                seen.add(code)
                unique_results.append((name, score, code))

        return [
            MasterMatchCandidate(name=name, code=code, score=score)
            for name, score, code in unique_results[:5]
        ]

    def _determine_status(self, score: float) -> str:
        """一致率に基づきステータスを決定"""
        if score >= MASTER_MATCH_OK_THRESHOLD:
            return "ok"
        elif score >= MASTER_MATCH_REVIEW_THRESHOLD:
            return "needs_review"
        else:
            return "ng"

    # === データロード ===

    async def _load_banks(self) -> None:
        """
        banks.jsonをロード（起動時）。
        キャッシュが有効ならファイルから、なければAPIからダウンロード。
        """
        # キャッシュディレクトリ作成
        ZENGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # キャッシュファイル有効性チェック
        if self._is_cache_valid(ZENGIN_BANKS_CACHE_FILE):
            logger.info("banks.json: キャッシュファイルからロード")
            data = self._read_cache_file(ZENGIN_BANKS_CACHE_FILE)
        else:
            logger.info("banks.json: APIからダウンロード")
            data = await self._download_json(ZENGIN_BANKS_URL)
            if data:
                self._write_cache_file(ZENGIN_BANKS_CACHE_FILE, data)
            elif ZENGIN_BANKS_CACHE_FILE.exists():
                # ダウンロード失敗時はキャッシュをフォールバック使用
                logger.warning("banks.json: ダウンロード失敗、キャッシュファイルをフォールバック使用")
                data = self._read_cache_file(ZENGIN_BANKS_CACHE_FILE)

        if not data:
            logger.error("banks.json: データ取得に完全失敗")
            return

        # パースしてメモリに格納
        self._parse_banks_data(data)

    async def _get_branches(self, bank_code: str) -> dict[str, BranchInfo]:
        """
        支店データをLazy Loadingで取得。
        メモリキャッシュ → ファイルキャッシュ → APIダウンロードの順で試行。
        """
        # メモリキャッシュ確認
        if bank_code in self._branches_cache:
            return self._branches_cache[bank_code]

        # ファイルキャッシュ確認
        ZENGIN_BRANCHES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = ZENGIN_BRANCHES_CACHE_DIR / f"{bank_code}.json"

        if self._is_cache_valid(cache_file):
            logger.debug(f"branches/{bank_code}.json: ファイルキャッシュからロード")
            data = self._read_cache_file(cache_file)
        else:
            logger.info(f"branches/{bank_code}.json: APIからダウンロード")
            url = ZENGIN_BRANCHES_URL_TEMPLATE.format(bank_code=bank_code)
            data = await self._download_json(url)
            if data:
                self._write_cache_file(cache_file, data)
            elif cache_file.exists():
                logger.warning(
                    f"branches/{bank_code}.json: ダウンロード失敗、キャッシュをフォールバック使用"
                )
                data = self._read_cache_file(cache_file)

        if not data:
            logger.warning(f"branches/{bank_code}.json: データ取得失敗")
            return {}

        # パースしてメモリキャッシュに格納
        branches = self._parse_branches_data(data)
        self._branches_cache[bank_code] = branches
        logger.debug(
            f"branches/{bank_code}.json: ロード完了 支店数={len(branches)}"
        )
        return branches

    def _parse_banks_data(self, data: dict) -> None:
        """banks.json APIレスポンスをパースしてメモリに格納"""
        for code, info in data.items():
            bank = BankInfo(
                code=code,
                name=info.get("name", ""),
                kana=info.get("kana", ""),
                hira=info.get("hira", ""),
                roma=info.get("roma", ""),
            )
            self._banks[code] = bank
            # 名前→コード逆引きインデックス
            if bank.name:
                self._bank_name_index[bank.name] = code

    def _parse_branches_data(self, data: dict) -> dict[str, BranchInfo]:
        """branches/{code}.json APIレスポンスをパース"""
        branches: dict[str, BranchInfo] = {}
        for code, info in data.items():
            branch = BranchInfo(
                code=code,
                name=info.get("name", ""),
                kana=info.get("kana", ""),
                hira=info.get("hira", ""),
                roma=info.get("roma", ""),
            )
            branches[code] = branch
        return branches

    # === キャッシュユーティリティ ===

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """キャッシュファイルが有効（存在＆TTL以内）か判定"""
        if not cache_file.exists():
            return False
        age = time.time() - cache_file.stat().st_mtime
        return age < ZENGIN_CACHE_TTL_SECONDS

    def _read_cache_file(self, cache_file: Path) -> Optional[dict]:
        """キャッシュファイルを読み込み"""
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"キャッシュファイル読み込み失敗: {cache_file} - {e}")
            return None

    def _write_cache_file(self, cache_file: Path, data: dict) -> None:
        """キャッシュファイルに書き込み"""
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.debug(f"キャッシュファイル書き込み完了: {cache_file}")
        except OSError as e:
            logger.error(f"キャッシュファイル書き込み失敗: {cache_file} - {e}")

    async def _download_json(self, url: str) -> Optional[dict]:
        """URLからJSONをダウンロード"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.error(f"JSONダウンロード失敗: {url} - {e}")
            return None
