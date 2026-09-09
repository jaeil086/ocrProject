"""
金融機関マスター変換スクリプト

タカノ部長から受領した bankmaster.xlsx を原本として、
既存の Zengin Code API と同一構造の JSON ファイル群を生成する。

生成物（単一ファイルで管理）:
  - banks.json    : {bank_code: {code, name, kana, hira, roma}}
  - branches.json : {bank_code: {branch_code: {code, name, kana, hira, roma}}}

エクセルの列構成（4列）:
  bank_code | branch_code | bank_name | branch_name

備考:
  - エクセルには kana/hira/roma が存在しないため空文字で埋める。
    照合ロジックは name のみを使用するため動作に影響しない。
  - コードはゼロ埋め文字列として扱う（銀行=4桁、支店=3桁が一般的だが、
    エクセルの値をそのまま文字列化して維持する）。

使用方法:
  python -m backend.scripts.build_zengin_master
  （オプションで入力/出力パスを指定可能。未指定時は config.py の設定を使用）
"""

import argparse
import json
import logging
from pathlib import Path

import openpyxl

from backend.config import (
    ZENGIN_BANKS_CACHE_FILE,
    ZENGIN_BRANCHES_CACHE_FILE,
    ZENGIN_MASTER_SOURCE_FILE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# エクセルの列見出し（1行目）
COL_BANK_CODE = "bank_code"
COL_BRANCH_CODE = "branch_code"
COL_BANK_NAME = "bank_name"
COL_BRANCH_NAME = "branch_name"


def _normalize(value: object) -> str:
    """セル値を文字列へ正規化（前後空白除去、None→空文字）"""
    if value is None:
        return ""
    return str(value).strip()


def _resolve_columns(header_row: tuple) -> dict[str, int]:
    """
    見出し行から列インデックスを解決する。
    列順が変わっても見出し名で対応できるようにする。
    """
    header = [_normalize(c).lower() for c in header_row]
    required = [COL_BANK_CODE, COL_BRANCH_CODE, COL_BANK_NAME, COL_BRANCH_NAME]

    index_map: dict[str, int] = {}
    for name in required:
        if name not in header:
            raise ValueError(
                f"エクセルに必須列 '{name}' が見つかりません。実際の見出し: {header}"
            )
        index_map[name] = header.index(name)
    return index_map


def build_master(
    source_file: Path,
    banks_output: Path,
    branches_output: Path,
) -> tuple[int, int]:
    """
    エクセルを読み込み、banks.json と branches.json を生成する。

    branches.json は銀行コードで入れ子にした単一ファイル:
        {bank_code: {branch_code: {code, name, kana, hira, roma}}}

    Returns:
        (銀行数, 支店総数)
    """
    if not source_file.exists():
        raise FileNotFoundError(f"マスター原本が見つかりません: {source_file}")

    logger.info(f"マスター原本を読み込み: {source_file}")
    wb = openpyxl.load_workbook(source_file, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]

    rows = ws.iter_rows(values_only=True)

    # 見出し行
    try:
        header_row = next(rows)
    except StopIteration:
        raise ValueError("エクセルが空です")

    cols = _resolve_columns(header_row)
    i_bank_code = cols[COL_BANK_CODE]
    i_branch_code = cols[COL_BRANCH_CODE]
    i_bank_name = cols[COL_BANK_NAME]
    i_branch_name = cols[COL_BRANCH_NAME]

    # 銀行マスター: {bank_code: {...}}
    banks: dict[str, dict[str, str]] = {}
    # 支店マスター: {bank_code: {branch_code: {...}}}
    branches: dict[str, dict[str, dict[str, str]]] = {}

    total_branches = 0
    skipped = 0

    for row in rows:
        bank_code = _normalize(row[i_bank_code])
        branch_code = _normalize(row[i_branch_code])
        bank_name = _normalize(row[i_bank_name])
        branch_name = _normalize(row[i_branch_name])

        # 銀行コードが無い行はスキップ（空行対策）
        if not bank_code:
            skipped += 1
            continue

        # 銀行マスター（初出のみ登録）
        if bank_code not in banks:
            banks[bank_code] = {
                "code": bank_code,
                "name": bank_name,
                "kana": "",
                "hira": "",
                "roma": "",
            }
            branches[bank_code] = {}

        # 支店マスター
        if branch_code:
            branches[bank_code][branch_code] = {
                "code": branch_code,
                "name": branch_name,
                "kana": "",
                "hira": "",
                "roma": "",
            }
            total_branches += 1

    wb.close()

    # === 出力 ===
    banks_output.parent.mkdir(parents=True, exist_ok=True)
    with open(banks_output, "w", encoding="utf-8") as f:
        json.dump(banks, f, ensure_ascii=False)
    logger.info(f"banks.json を出力: {banks_output} (銀行数={len(banks)})")

    # 支店マスターは単一ファイル（銀行コードで入れ子）として出力
    branches_output.parent.mkdir(parents=True, exist_ok=True)
    with open(branches_output, "w", encoding="utf-8") as f:
        json.dump(branches, f, ensure_ascii=False)

    logger.info(
        f"branches.json を出力: {branches_output} "
        f"(銀行数={len(branches)}, 支店総数={total_branches})"
    )

    if skipped:
        logger.info(f"空行スキップ数: {skipped}")

    return len(banks), total_branches


def main() -> None:
    parser = argparse.ArgumentParser(
        description="bankmaster.xlsx から金融機関マスターJSONを生成する"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ZENGIN_MASTER_SOURCE_FILE,
        help=f"入力エクセルパス（既定: {ZENGIN_MASTER_SOURCE_FILE}）",
    )
    parser.add_argument(
        "--banks-output",
        type=Path,
        default=ZENGIN_BANKS_CACHE_FILE,
        help=f"banks.json 出力パス（既定: {ZENGIN_BANKS_CACHE_FILE}）",
    )
    parser.add_argument(
        "--branches-output",
        type=Path,
        default=ZENGIN_BRANCHES_CACHE_FILE,
        help=f"branches.json 出力パス（既定: {ZENGIN_BRANCHES_CACHE_FILE}）",
    )
    args = parser.parse_args()

    bank_count, branch_count = build_master(
        args.source, args.banks_output, args.branches_output
    )
    logger.info(
        f"変換完了: 銀行数={bank_count}, 支店総数={branch_count}"
    )


if __name__ == "__main__":
    main()
