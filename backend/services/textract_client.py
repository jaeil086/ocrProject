"""
Amazon Textract クライアント

Amazon Textract AnalyzeDocument APIを呼び出し、
OCR結果をTextractResultモデルに変換する。
tenacityによるリトライ（最大3回、指数バックオフ）を設定する。
"""

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import (
    AWS_REGION,
    AWS_TEXTRACT_SERVICE,
    TEXTRACT_MAX_RETRIES,
    TEXTRACT_RETRY_MAX_WAIT,
    TEXTRACT_RETRY_MIN_WAIT,
)
from backend.models.schemas import TextractLine, TextractResult, TextractWord


class TextractClient:
    """Amazon Textract API呼び出しクライアント"""

    def __init__(self):
        self.client = boto3.client(
            AWS_TEXTRACT_SERVICE, region_name=AWS_REGION
        )

    @retry(
        stop=stop_after_attempt(TEXTRACT_MAX_RETRIES),
        wait=wait_exponential(
            min=TEXTRACT_RETRY_MIN_WAIT, max=TEXTRACT_RETRY_MAX_WAIT
        ),
    )
    async def analyze_document(self, image_bytes: bytes) -> TextractResult:
        """
        Textract AnalyzeDocument API呼び出し

        機能:
        - FORMS: Key-Valueペア認識
        - TABLES: テーブル構造認識
        - 各単語にConfidence Score付与

        Args:
            image_bytes: 分析対象の画像バイナリ（PNG形式）

        Returns:
            TextractResult: OCR認識結果（行、フォーム、テーブル）

        Raises:
            botocore.exceptions.ClientError: Textract API呼び出し失敗時
        """
        response = self.client.analyze_document(
            Document={"Bytes": image_bytes},
            FeatureTypes=["FORMS", "TABLES"],
        )
        return self._parse_response(response)

    def _parse_response(self, response: dict) -> TextractResult:
        """
        Textractレスポンスをパースし、TextractResultモデルに変換する

        Textractのレスポンスからブロック情報を抽出し、
        LINE、KEY_VALUE_SET、TABLE、WORDブロックを適切に処理する。
        LINEブロックに属するWORDブロックはRelationshipsから紐付ける。

        Args:
            response: Textract AnalyzeDocument APIのレスポンスdict

        Returns:
            TextractResult: パース済みのOCR認識結果
        """
        blocks = response.get("Blocks", [])

        # ブロックIDをキーとするインデックスを構築
        block_map: dict[str, dict] = {}
        for block in blocks:
            block_map[block["Id"]] = block

        lines: list[TextractLine] = []
        forms: list[dict] = []
        tables: list[dict] = []

        for block in blocks:
            block_type = block.get("BlockType", "")

            if block_type == "LINE":
                # LINEブロックに含まれるWORDを取得
                words = self._extract_words(block, block_map)
                lines.append(
                    TextractLine(
                        text=block.get("Text", ""),
                        confidence=block.get("Confidence", 0.0),
                        words=words,
                    )
                )
            elif block_type == "KEY_VALUE_SET":
                forms.append(block)
            elif block_type == "TABLE":
                tables.append(block)

        return TextractResult(lines=lines, forms=forms, tables=tables)

    def _extract_words(
        self, line_block: dict, block_map: dict[str, dict]
    ) -> list[TextractWord]:
        """
        LINEブロックに含まれるWORDブロックを抽出する

        Relationshipsフィールドから子要素（CHILD）のWORDブロックIDを取得し、
        TextractWordモデルに変換する。

        Args:
            line_block: LINEタイプのブロックdict
            block_map: ブロックIDをキーとするインデックス

        Returns:
            list[TextractWord]: LINE内の単語リスト
        """
        words: list[TextractWord] = []
        relationships = line_block.get("Relationships", [])

        for relationship in relationships:
            if relationship.get("Type") == "CHILD":
                for child_id in relationship.get("Ids", []):
                    child_block = block_map.get(child_id)
                    if (
                        child_block
                        and child_block.get("BlockType") == "WORD"
                    ):
                        # BoundingBoxの取得（Geometryから）
                        geometry = child_block.get("Geometry", {})
                        bounding_box = geometry.get(
                            "BoundingBox",
                            {
                                "Left": 0.0,
                                "Top": 0.0,
                                "Width": 0.0,
                                "Height": 0.0,
                            },
                        )

                        words.append(
                            TextractWord(
                                text=child_block.get("Text", ""),
                                confidence=child_block.get(
                                    "Confidence", 0.0
                                ),
                                bounding_box=bounding_box,
                            )
                        )

        return words
