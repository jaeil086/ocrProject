"""
Amazon Bedrock Claudeクライアント

Claude Sonnet 4.5を「OCR+文書理解エンジン」として利用する。
PDFから変換した画像を直接Claudeに渡し、口座振替依頼書のフィールドを抽出する。
Textractは使用しない（MVP構成）。
"""

import base64
import json
import logging

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import (
    AWS_BEDROCK_SERVICE,
    AWS_REGION,
    BEDROCK_MAX_RETRIES,
    BEDROCK_INFERENCE_PROFILE_ID,
    BEDROCK_RETRY_MAX_WAIT,
    BEDROCK_RETRY_MIN_WAIT,
    CLAUDE_MAX_TOKENS,
    CONFIDENCE_THRESHOLD,
)
from backend.models.enums import ConfidenceLevel, FormType
from backend.models.schemas import ClaudeExtractionResult, OcrField

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Amazon Bedrock Claude — 画像から直接OCR+フィールド抽出"""

    def __init__(self):
        self.client = boto3.client(
            AWS_BEDROCK_SERVICE, region_name=AWS_REGION
        )

    @retry(
        stop=stop_after_attempt(BEDROCK_MAX_RETRIES),
        wait=wait_exponential(min=BEDROCK_RETRY_MIN_WAIT, max=BEDROCK_RETRY_MAX_WAIT),
    )
    async def extract_fields_from_image(
        self, image_bytes: bytes
    ) -> ClaudeExtractionResult:
        """
        画像から直接フィールドを抽出する（Textract不使用）

        Args:
            image_bytes: PNG画像バイナリ

        Returns:
            ClaudeExtractionResult: 抽出結果
        """
        prompt = self._build_prompt()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        response = self.client.invoke_model(
            modelId=BEDROCK_INFERENCE_PROFILE_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": CLAUDE_MAX_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }),
        )

        return self._parse_claude_response(response)

    def _build_prompt(self) -> str:
        """Claude用プロンプト — 3カテゴリチェック体系（fields配列形式）"""
        return f"""あなたは日本の金融帳票を読み取る専門OCRシステムです。
この画像は「預金口座振替依頼書（自動払込利用申込書）」です。

以下の3カテゴリのチェック項目について、画像を読み取り結果をJSON形式で出力してください。

【カテゴリ1: 〇印チェック】
以下の項目に〇印（丸で囲む）が付いているか確認してください。

- 収納代行会社名: 帳票上部に「1 きらぼしシステム株式会社」「2 三菱UFJファクター株式会社」の選択肢があり、どちらかに〇印があるか確認。〇があれば選択された会社名をvalueに、なければ"未選択"をvalueに設定。
- 預金種目: 「1 普通」「2 当座」のどちらかに〇印があるか確認。〇があれば種目名をvalueに、なければ"未選択"をvalueに設定。
- 届出印: 帳票右側の届出印欄に印鑑（朱肉の印影）が押されているか確認。押されていれば"あり"、なければ"なし"をvalueに設定。

【カテゴリ2: 未入力チェック】
以下の項目に記入があるかどうかを確認してください。
記入がある場合はvalueに"記入済"、記入がない場合は"未記入"をvalueに設定。

- 預金者名フリガナ: フリガナ欄にカタカナが記入されているか
- 預金者名氏名: 氏名欄に名前が記入されているか
- 口座番号: 「※ゆうちょ銀行以外の金融機関ご利用の場合」セクションの口座番号欄に数字が記入されているか
- 記号番号: 「※ゆうちょ銀行ご利用の場合」セクションの「記号」欄と「番号」欄を確認。
  ※ この欄に手書きの数字が記入されている場合のみ"記入済"。
  ※ 印刷されたラベル文字（「記号」「番号」等）や空のマス目だけの場合は"未記入"。
  ※ 「00100-3-578806」のような加入者番号は別の欄なので混同しないこと。

【カテゴリ3: 記入内容の抽出】

- 銀行番号:
  「※ゆうちょ銀行以外の金融機関ご利用の場合」セクション内で「コード」「銀行番号」と書かれた欄のマス目に記入された4桁の数字。
  ※ 必ず4桁で出力してください。先頭が0の場合も0を含めて"0009"のように出力。
  ※ このマス目は通常、銀行名の下にあります。

- 支店番号:
  同セクション内で「店番号」と書かれた欄のマス目に記入された3桁の数字。
  ※ 必ず3桁で出力してください。先頭が0の場合も0を含めて"003"のように出力。

- 委託者番号:
  帳票下部「収納企業使用欄」の「委託者番号・契約者番号」のマス目を確認。
  このマス目は途中に太い仕切り線で2つの区画に分かれています。
  左側の区画（5マス）の数字を読み取ってください。

- 契約者番号:
  同じ「委託者番号・契約者番号」のマス目で、太い仕切り線の右側の区画の数字を読み取ってください。
  ※ 左側区画とは別の数字です。右側区画だけを読んでください。

【出力フォーマット（JSON）】
以下のJSONフォーマットのみを出力してください。説明文や補足は不要です。
```json
{{{{
  "form_type": "general",
  "fields": [
    {{{{"field_name": "収納代行会社名", "value": "選択された会社名 or 未選択", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "預金種目", "value": "普通 or 当座 or 未選択", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "届出印", "value": "あり or なし", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "預金者名フリガナ", "value": "記入済 or 未記入", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "預金者名氏名", "value": "記入済 or 未記入", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "口座番号", "value": "記入済 or 未記入", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "記号番号", "value": "記入済 or 未記入", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "銀行番号", "value": "4桁の数字（0埋め）例:0009", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "支店番号", "value": "3桁の数字（0埋め）例:681", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "委託者番号", "value": "読み取った数字列", "confidence_score": 90, "needs_review": false}}}},
    {{{{"field_name": "契約者番号", "value": "読み取った数字列", "confidence_score": 90, "needs_review": false}}}}
  ],
  "deficiency_notes": [],
  "correction_suggestions": {{{{}}}}
}}}}
```

【重要な注意事項】
- confidence_scoreは読み取りの確信度（鮮明に読める=90-100、やや不鮮明=50-89、ほぼ読めない=0-49）
- needs_reviewはconfidence_scoreが{CONFIDENCE_THRESHOLD}未満の場合にtrue
- 銀行番号は必ず4桁、支店番号は必ず3桁で、先頭の0を省略しないでください
- 読み取りが不鮮明でも、見えている数字をそのまま出力してください
- JSON以外の文字列は出力しないでください"""

    def _parse_claude_response(self, response) -> ClaudeExtractionResult:
        """Claude応答をパースしてClaudeExtractionResultに変換"""
        response_body = json.loads(response["body"].read())

        content = response_body.get("content", [])
        text_response = ""
        for block in content:
            if block.get("type") == "text":
                text_response = block.get("text", "")
                break

        json_str = self._extract_json(text_response)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Claude応答のJSONパースに失敗: {e}")
            logger.error(f"応答テキスト: {text_response[:500]}")
            raise ValueError(f"Claude応答のJSONパースに失敗しました: {e}")

        form_type = FormType(data.get("form_type", "general"))

        extracted_fields = []
        for field_data in data.get("fields", []):
            confidence_score = float(field_data.get("confidence_score", 100))
            confidence_level = (
                ConfidenceLevel.LOW
                if confidence_score < CONFIDENCE_THRESHOLD
                else ConfidenceLevel.HIGH
            )
            extracted_fields.append(
                OcrField(
                    field_name=field_data.get("field_name", ""),
                    value=field_data.get("value"),
                    confidence_score=confidence_score,
                    confidence_level=confidence_level,
                    is_confirmed=False,
                    corrected_value=None,
                )
            )

        needs_review_fields = [
            field_data.get("field_name", "")
            for field_data in data.get("fields", [])
            if field_data.get("needs_review", False)
        ]

        deficiency_notes = data.get("deficiency_notes", [])
        correction_suggestions = data.get("correction_suggestions", {})

        return ClaudeExtractionResult(
            form_type=form_type,
            extracted_fields=extracted_fields,
            needs_review_fields=needs_review_fields,
            deficiency_notes=deficiency_notes,
            correction_suggestions=correction_suggestions,
        )

    def _extract_json(self, text: str) -> str:
        """テキストからJSON部分を抽出"""
        if "```json" in text:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            return text[start:end].strip()

        if "```" in text:
            start = text.index("```") + len("```")
            end = text.index("```", start)
            return text[start:end].strip()

        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]

        return text.strip()
