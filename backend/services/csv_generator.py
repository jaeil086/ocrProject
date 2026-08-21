"""
CSV/Excel生成サービス

OcrDocumentからpandas DataFrameを経由してCSVバイナリ/Excel(xlsx)を生成する。
出力形式は check-results に合わせた構成。
ファイル命名規則に基づくファイル名生成も担当する。

Excel出力時はチェック項目に色分けを適用:
  - NG: 赤色フォント
  - OK: 青色フォント
  - 要確認: オレンジフォント
"""

import io
from datetime import datetime
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

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
    "お届出印金融機関",
    "銀行名",
    "支店名",
    "預金種目",
    "口座番号",
    "銀行番号",
    "店番号",
    "ゆうちょ記号",
    "ゆうちょ番号",
    "振替日",
    "委託者番号",
    "契約者番号",
    "委託者名",
    "料金等の種類",
    # チェック結果カラム
    "預金者氏名_チェック",
    "預金者フリガナ_チェック",
    "お届出印金融機関_チェック",
    "銀行名_チェック",
    "支店名_チェック",
    "預金種目_チェック",
    "口座番号_チェック",
    "銀行番号_チェック",
    "店番号_チェック",
    "ゆうちょ記号_チェック",
    "ゆうちょ番号_チェック",
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
    "お届出印金融機関",
    "銀行名",
    "支店名",
    "預金種目",
    "口座番号",
    "銀行番号",
    "店番号",
    "ゆうちょ記号",
    "ゆうちょ番号",
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

        # Excelで先頭0が消えないよう数値フィールドを保護するフィールド一覧
        NUMERIC_PRESERVE_FIELDS = {
            "口座番号", "銀行番号", "店番号", "委託者番号", "契約者番号",
            "ゆうちょ記号", "ゆうちょ番号",
        }

        def get_value(name: str) -> str:
            """フィールド値を取得（修正値優先）"""
            field = field_map.get(name)
            if field is None:
                return ""
            value = field.corrected_value or field.value or ""
            # お届出印金融機関は「あり」→OK、「なし」→NGに変換
            if name == "お届出印金融機関":
                return "OK" if value == "あり" else "NG"
            # 数値フィールドの先頭0を保持するためExcel数式形式で出力
            if value and name in NUMERIC_PRESERVE_FIELDS:
                return f'="{value}"'
            return value

        def get_check(name: str) -> str:
            """
            フィールドのチェック結果を返す
            - お届出印金融機関: 「あり」→OK、それ以外→NG
            - 銀行名: 「（x）」を含む場合→NG（種別未選択）
            - 銀行関連フィールド（銀行名〜店番号）とゆうちょ関連（ゆうちょ記号・番号）は排他:
              ゆうちょ側に記入がある場合、銀行側が空欄なのは正常（"-"を返す）
              銀行側に記入がある場合、ゆうちょ側が空欄なのは正常（"-"を返す）
            - 値が正常に取得できている場合: "OK"
            - 値がない場合: "NG"
            - Confidence低い場合: "要確認"
            """
            field = field_map.get(name)
            # お届出印金融機関は「あり」/「なし」で判定
            if name == "お届出印金融機関":
                if field and field.value == "あり":
                    return "OK"
                return "NG"

            # 銀行系フィールドとゆうちょ系フィールドの排他判定
            bank_fields = {"銀行名", "支店名", "預金種目", "口座番号", "銀行番号", "店番号"}
            yucho_fields = {"ゆうちょ記号", "ゆうちょ番号"}

            # ゆうちょ側に値があるか判定
            has_yucho = any(
                (f := field_map.get(fn)) and f.value
                for fn in yucho_fields
            )
            # 銀行側に値があるか判定
            has_bank = any(
                (f := field_map.get(fn)) and f.value
                for fn in bank_fields
            )

            # 排他判定: 相手側に記入があり自分側が空欄の場合は正常（"-"）
            if name in bank_fields:
                if (field is None or not field.value) and has_yucho:
                    return "-"
            if name in yucho_fields:
                if (field is None or not field.value) and has_bank:
                    return "-"

            # 銀行番号・店番号は必須確認項目
            # 値がない場合は「NG」（未記入として扱うが、確認が必要）
            optional_code_fields = {"銀行番号", "店番号"}
            if name in optional_code_fields:
                if field is None or not field.value:
                    return "NG"
                if field.confidence_level == ConfidenceLevel.LOW:
                    return "要確認"
                return "OK"

            # 銀行名は「（x）」を含む場合NG（種別未選択）
            if name == "銀行名":
                if field is None or not field.value:
                    return "NG"
                if "（x）" in field.value:
                    return "NG"
                if field.confidence_level == ConfidenceLevel.LOW:
                    return "要確認"
                return "OK"
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
            "お届出印金融機関": get_value("お届出印金融機関"),
            "銀行名": get_value("銀行名"),
            "支店名": get_value("支店名"),
            "預金種目": get_value("預金種目"),
            "口座番号": get_value("口座番号"),
            "銀行番号": get_value("銀行番号"),
            "店番号": get_value("店番号"),
            "ゆうちょ記号": get_value("ゆうちょ記号"),
            "ゆうちょ番号": get_value("ゆうちょ番号"),
            "振替日": get_value("振替日"),
            "委託者番号": get_value("委託者番号"),
            "契約者番号": get_value("契約者番号"),
            "委託者名": get_value("委託者名"),
            "料金等の種類": get_value("料金等の種類"),
            # チェック結果
            "預金者氏名_チェック": get_check("預金者氏名"),
            "預金者フリガナ_チェック": get_check("預金者フリガナ"),
            "お届出印金融機関_チェック": get_check("お届出印金融機関"),
            "銀行名_チェック": get_check("銀行名"),
            "支店名_チェック": get_check("支店名"),
            "預金種目_チェック": get_check("預金種目"),
            "口座番号_チェック": get_check("口座番号"),
            "銀行番号_チェック": get_check("銀行番号"),
            "店番号_チェック": get_check("店番号"),
            "ゆうちょ記号_チェック": get_check("ゆうちょ記号"),
            "ゆうちょ番号_チェック": get_check("ゆうちょ番号"),
            "振替日_チェック": get_check("振替日"),
            "委託者番号_チェック": get_check("委託者番号"),
            "契約者番号_チェック": get_check("契約者番号"),
            "委託者名_チェック": get_check("委託者名"),
            "料金等の種類_チェック": get_check("料金等の種類"),
        }

        return row

    def generate_excel(self, rows: list[dict]) -> bytes:
        """
        複数行のデータからExcel(xlsx)バイナリを生成

        チェック項目に色分けを適用:
          - NG: 赤色フォント（太字）
          - OK: 青色フォント
          - 要確認: オレンジフォント（太字）

        Args:
            rows: _build_rowで生成されたdict行データのリスト

        Returns:
            bytes: xlsxバイナリ
        """
        df = pd.DataFrame(rows, columns=CSV_COLUMNS)

        wb = Workbook()
        ws = wb.active
        ws.title = "OCR結果"

        # フォント定義
        font_ng = Font(color="FF0000", bold=True)       # 赤色（NG）
        font_ok = Font(color="0000FF", bold=False)      # 青色（OK）
        font_review = Font(color="FF8C00", bold=True)   # オレンジ（要確認）
        font_header = Font(bold=True, color="FFFFFF")
        fill_header = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

        # ヘッダー書き込み
        for col_idx, col_name in enumerate(CSV_COLUMNS, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center")

        # データ書き込み
        for row_idx, row_data in enumerate(rows, 2):
            for col_idx, col_name in enumerate(CSV_COLUMNS, 1):
                value = row_data.get(col_name, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=value)

                # チェック項目に色分け適用
                if col_name.endswith("_チェック"):
                    if value == "NG":
                        cell.font = font_ng
                    elif value == "OK":
                        cell.font = font_ok
                    elif value == "要確認":
                        cell.font = font_review
                # お届出印金融機関の値カラムにも色分け適用（OK/NG表示）
                elif col_name == "お届出印金融機関":
                    if value == "NG":
                        cell.font = font_ng
                    elif value == "OK":
                        cell.font = font_ok

        # 列幅を自動調整（おおよそ）
        for col_idx, col_name in enumerate(CSV_COLUMNS, 1):
            # 日本語文字は幅2として概算
            width = max(len(col_name) * 1.5, 8)
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

        # バイナリ出力
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def build_row(self, document: OcrDocument) -> dict:
        """外部から呼び出し可能な行データ構築（バッチCSV用）"""
        return self._build_row(document)
