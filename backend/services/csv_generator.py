"""
CSV生成サービス

OcrDocumentからpandas DataFrameを経由してCSVバイナリを生成する。
出力形式は check-results.csv に合わせた構成。
ファイル命名規則に基づくCSVファイル名生成も担当する。
"""

import io
from datetime import datetime
from typing import Optional

import pandas as pd

from backend.models.enums import ConfidenceLevel
from backend.models.schemas import OcrDocument


# CSVカラム定義（check-results形式）
# 前半: 抽出値、後半: 各フィールドのチェック結果
CSV_COLUMNS = [
    "処理日時",
    "入力ファイル名",
    # 抽出フィールド
    "預金者氏名",
    "預金者フリガナ",
    "銀行名",
    "支店名",
    "預金種目",
    "口座番号",
    "銀行番号",
    "店番号",
    "振替日",
    "委託者番号",
    "契約者番号",
    "委託者名",
    "料金等の種類",
    # チェック結果カラム
    "預金者氏名_チェック",
    "預金者フリガナ_チェック",
    "銀行名_チェック",
    "支店名_チェック",
    "預金種目_チェック",
    "口座番号_チェック",
    "銀行番号_チェック",
    "店番号_チェック",
    "振替日_チェック",
    "委託者番号_チェック",
    "契約者番号_チェック",
    "委託者名_チェック",
    "料金等の種類_チェック",
]

# チェック対象フィールド名（抽出フィールドの順序に対応）
CHECK_FIELDS = [
    "預金者氏名",
    "預金者フリガナ",
    "銀行名",
    "支店名",
    "預金種目",
    "口座番号",
    "銀行番号",
    "店番号",
    "振替日",
    "委託者番号",
    "契約者番号",
    "委託者名",
    "料金等の種類",
]


def _generate_filename(
    file_id: str,
    consignor_number: Optional[str],
    contract_number: Optional[str],
    has_review_items: bool,
    extension: str,
) -> str:
    """
    ファイル命名規則に基づくファイル名生成

    パターン:
    1. 委託者番号または契約番号が未取得 → UNKNOWN_{FileID}.{ext}
    2. 要確認項目あり →★要確認_{委託者番号}_{契約番号}.{ext}
    3. 通常 → {委託者番号}_{契約番号}.{ext}
    """
    if not consignor_number or not contract_number:
        return f"UNKNOWN_{file_id}.{extension}"

    if has_review_items:
        return f"★要確認_{consignor_number}_{contract_number}.{extension}"

    return f"{consignor_number}_{contract_number}.{extension}"


class CsvGenerator:
    """CSV生成サービス（pandas使用、check-results形式）"""

    def generate(self, document: OcrDocument) -> bytes:
        """
        OcrDocumentからCSVバイナリを生成

        - pandas DataFrameを経由してCSV出力
        - 文字コードはUTF-8 with BOM（Excel互換）
        - check-results.csv形式に準拠
        """
        row = self._build_row(document)
        df = pd.DataFrame([row], columns=CSV_COLUMNS)

        buffer = io.BytesIO()
        # UTF-8 BOM付きで出力（Excelで開いても文字化けしない）
        buffer.write(b'\xef\xbb\xbf')
        df.to_csv(buffer, index=False, encoding="utf-8", mode="a")
        return buffer.getvalue()

    def generate_filename(self, document: OcrDocument) -> str:
        """CSV出力ファイル名生成"""
        has_review_items = any(
            f.confidence_level == ConfidenceLevel.LOW and not f.is_confirmed
            for f in document.fields
        )

        return _generate_filename(
            file_id=document.file_id,
            consignor_number=document.consignor_number,
            contract_number=document.contract_number,
            has_review_items=has_review_items,
            extension="csv",
        )

    def _build_row(self, document: OcrDocument) -> dict:
        """ドキュメントからCSV行データを構築（check-results形式）"""
        field_map = {f.field_name: f for f in document.fields}

        def get_value(name: str) -> str:
            """フィールド値を取得（修正値優先）"""
            field = field_map.get(name)
            if field is None:
                return ""
            return field.corrected_value or field.value or ""

        def get_check(name: str) -> str:
            """
            フィールドのチェック結果を返す
            - 値が正常に取得できている場合: "OK"
            - 値がない場合: "NG"
            - Confidence低い場合: "要確認"
            """
            field = field_map.get(name)
            if field is None or not field.value:
                return "NG"
            if field.confidence_level == ConfidenceLevel.LOW:
                return "要確認"
            return "OK"

        # 処理日時は「年-月-日 時:分:秒」形式（ユーザーが読みやすい形式）
        processing_time = document.updated_at.strftime("%Y-%m-%d %H:%M:%S")

        row = {
            "処理日時": processing_time,
            "入力ファイル名": document.original_filename,
            # 抽出フィールド
            "預金者氏名": get_value("預金者氏名"),
            "預金者フリガナ": get_value("預金者フリガナ"),
            "銀行名": get_value("銀行名"),
            "支店名": get_value("支店名"),
            "預金種目": get_value("預金種目"),
            "口座番号": get_value("口座番号"),
            "銀行番号": get_value("銀行番号"),
            "店番号": get_value("店番号"),
            "振替日": get_value("振替日"),
            "委託者番号": get_value("委託者番号"),
            "契約者番号": get_value("契約者番号"),
            "委託者名": get_value("委託者名"),
            "料金等の種類": get_value("料金等の種類"),
            # チェック結果
            "預金者氏名_チェック": get_check("預金者氏名"),
            "預金者フリガナ_チェック": get_check("預金者フリガナ"),
            "銀行名_チェック": get_check("銀行名"),
            "支店名_チェック": get_check("支店名"),
            "預金種目_チェック": get_check("預金種目"),
            "口座番号_チェック": get_check("口座番号"),
            "銀行番号_チェック": get_check("銀行番号"),
            "店番号_チェック": get_check("店番号"),
            "振替日_チェック": get_check("振替日"),
            "委託者番号_チェック": get_check("委託者番号"),
            "契約者番号_チェック": get_check("契約者番号"),
            "委託者名_チェック": get_check("委託者名"),
            "料金等の種類_チェック": get_check("料金等の種類"),
        }

        return row
