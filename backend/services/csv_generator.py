"""
CSV生成サービス

OcrDocumentからpandas DataFrameを経由してShift_JISエンコードのCSVバイナリを生成する。
ファイル命名規則に基づくCSVファイル名生成も担当する。
"""

import io
from typing import Optional

import pandas as pd

from backend.models.enums import ConfidenceLevel
from backend.models.schemas import OcrDocument


# CSVカラム定義（3カテゴリチェック体系）
CSV_COLUMNS = [
    "FileID",
    # カテゴリ1: 〇印チェック
    "収納代行会社名",
    "預金種目",
    "届出印",
    # カテゴリ2: 未入力チェック
    "預金者名フリガナ",
    "預金者名氏名",
    "口座番号",
    "記号番号",
    # カテゴリ3: 記入内容抽出
    "銀行番号",
    "支店番号",
    "委託者番号",
    "契約者番号",
    # メタ情報
    "ステータス",
    "備考",
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
    2. 要確認項目あり → {FileID}_★要確認_{委託者番号}_{契約番号}.{ext}
    3. 通常 → {FileID}_{委託者番号}_{契約番号}.{ext}
    """
    if not consignor_number or not contract_number:
        return f"UNKNOWN_{file_id}.{extension}"

    if has_review_items:
        return f"{file_id}_★要確認_{consignor_number}_{contract_number}.{extension}"

    return f"{file_id}_{consignor_number}_{contract_number}.{extension}"


class CsvGenerator:
    """CSV生成サービス（pandas使用）"""

    def generate(self, document: OcrDocument) -> bytes:
        """
        OcrDocumentからCSVバイナリを生成

        - pandas DataFrameを経由してCSV出力
        - 文字コードはShift_JIS
        - 不備項目がある場合は備考列に記録
        """
        row = self._build_row(document)
        df = pd.DataFrame([row], columns=CSV_COLUMNS)

        buffer = io.BytesIO()
        df.to_csv(buffer, index=False, encoding="shift_jis")
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
        """ドキュメントからCSV行データを構築（3カテゴリ体系）"""
        field_map = {f.field_name: f for f in document.fields}

        def get_value(name: str) -> str:
            """フィールド値を取得（修正値優先）"""
            field = field_map.get(name)
            if field is None:
                return ""
            return field.corrected_value or field.value or ""

        remarks = "; ".join(
            [f"{e.field_name}: {e.message}" for e in document.validation_errors]
        )

        return {
            "FileID": document.file_id,
            # カテゴリ1: 〇印チェック
            "収納代行会社名": get_value("収納代行会社名"),
            "預金種目": get_value("預金種目"),
            "届出印": get_value("届出印"),
            # カテゴリ2: 未入力チェック
            "預金者名フリガナ": get_value("預金者名フリガナ"),
            "預金者名氏名": get_value("預金者名氏名"),
            "口座番号": get_value("口座番号"),
            "記号番号": get_value("記号番号"),
            # カテゴリ3: 記入内容抽出
            "銀行番号": get_value("銀行番号"),
            "支店番号": get_value("支店番号"),
            "委託者番号": get_value("委託者番号"),
            "契約者番号": get_value("契約者番号"),
            # メタ情報
            "ステータス": document.status.value,
            "備考": remarks,
        }
