"""
Amazon Bedrock Claudeクライアント

Claude Sonnet 4.5を「OCR+文書理解エンジン」として利用する。
2段階OCR方式:
  Step1: 画像内の全テキストを読み取り
  Step2: 読み取りテキストからフィールドを構造化抽出
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
    """Amazon Bedrock Claude — 2段階OCR方式"""

    def __init__(self):
        self.client = boto3.client(
            AWS_BEDROCK_SERVICE, region_name=AWS_REGION
        )

    async def extract_fields_from_image(
        self, image_bytes: bytes
    ) -> ClaudeExtractionResult:
        """
        2段階OCR:
        Step1: 画像から全テキストを抽出
        Step2: テキストから構造化フィールドを抽出
        """
        # Step1: 全テキストOCR
        raw_text = await self._step1_full_ocr(image_bytes)
        logger.info(f"Step1 OCR結果（先頭300文字）: {raw_text[:300]}")

        # Step2: テキストからフィールド抽出
        result = await self._step2_extract_fields(raw_text, image_bytes)
        return result

    @retry(
        stop=stop_after_attempt(BEDROCK_MAX_RETRIES),
        wait=wait_exponential(min=BEDROCK_RETRY_MIN_WAIT, max=BEDROCK_RETRY_MAX_WAIT),
    )
    async def _step1_full_ocr(self, image_bytes: bytes) -> str:
        """Step1: 画像内の全テキストを読み取る"""
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        # JPEG判定（先頭バイトで判別）
        media_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"

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
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": self._step1_prompt()},
                        ],
                    }
                ],
            }),
        )

        response_body = json.loads(response["body"].read())
        content = response_body.get("content", [])
        for block in content:
            if block.get("type") == "text":
                return block.get("text", "")
        return ""

    @retry(
        stop=stop_after_attempt(BEDROCK_MAX_RETRIES),
        wait=wait_exponential(min=BEDROCK_RETRY_MIN_WAIT, max=BEDROCK_RETRY_MAX_WAIT),
    )
    async def _step2_extract_fields(
        self, raw_text: str, image_bytes: bytes
    ) -> ClaudeExtractionResult:
        """Step2: OCRテキスト+画像からフィールドを構造化抽出"""
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        media_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"

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
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": self._step2_prompt(raw_text),
                            },
                        ],
                    }
                ],
            }),
        )

        return self._parse_response(response)

    def _step1_prompt(self) -> str:
        """Step1: 全テキスト読み取りプロンプト"""
        return """この画像は日本の「預金口座振替依頼書」です。
画像内に書かれている全ての文字（印字・手書き・スタンプ含む）を、
上から下、左から右の順序でそのまま書き起こしてください。
マス目に1文字ずつ書かれている数字も全て読み取ってください。
読み取れた文字をそのまま出力してください。"""

    def _step2_prompt(self, raw_text: str) -> str:
        """Step2: フィールド抽出プロンプト"""
        return f"""あなたは日本の金融帳票OCRエンジンです。
下記は画像から読み取ったテキストです。画像も参照しながら、各フィールドの値を抽出してください。

【読み取りテキスト】
{raw_text}

【抽出ルール】
以下の各フィールドについて、実際に認識した文字列をそのまま返してください。
「記入済」「未記入」ではなく、読み取った実際の文字・数字を返すこと。
判別不能の場合のみ null を返してください。

1. 収納代行会社名:
   帳票上部「収納代行会社名」の横に「1 きらぼしシステム株式会社」「2 三菱UFJファクター株式会社」がある。
   〇印で選択されている方の会社名を返す。選択なしなら null。

2. 預金種目:
   「預金種目」欄で「1.普通」「2.当座」のどちらに〇印があるか。
   選択されている種目名を返す。選択なしなら null。

3. 届出印:
   帳票右側「届出印」欄に印影があれば "あり"、なければ "なし"。

4. 預金者名フリガナ:
   「フリガナ」欄に記入されているカタカナ文字列をそのまま返す。空欄なら null。

5. 預金者名氏名:
   「氏名」欄に記入されている名前をそのまま返す。法人の場合は法人名・肩書・代表者名を含む。空欄なら null。

6. 口座番号:
   「口座番号」欄（ゆうちょ以外）に記入されている7桁の数字をそのまま返す。
   ※ 口座番号は必ず7桁です。7桁で返してください。空欄なら null。

7. 記号番号:
   「※ゆうちょ銀行ご利用の場合」セクションの記号・番号欄に手書き記入された数字。空欄なら null。
   ※ 印刷済みの「00100-3-578806」等の加入者番号とは異なるので注意。

8. 銀行番号:
   「※ゆうちょ銀行以外の金融機関ご利用の場合」セクション内、金融機関名の下にある「コード」欄の4桁数字。
   先頭0を省略せず4桁で返す（例: "0137"）。

9. 支店番号:
   同セクション内、支店名の下にある「店番号」欄の3桁数字。
   先頭0を省略せず3桁で返す（例: "209"）。

10. 委託者番号:
    帳票下部「収納企業使用欄」の「委託者番号・契約者番号」マス目。
    このマス目は10桁あり、太い仕切り線で前半5桁と後半5桁に分かれている。
    前半5桁の数字を返す。

11. 契約者番号:
    同マス目の後半5桁の数字を返す。
    ※ 前半5桁(委託者番号)とは別の数字。仕切り線の右側を読む。

【出力形式】
以下のJSON形式のみ出力。説明文は不要。
各フィールドに confidence (0-100) を付与すること。

{{"収納代行会社名":{{"value":"","confidence":0}},"預金種目":{{"value":"","confidence":0}},"届出印":{{"value":"","confidence":0}},"預金者名フリガナ":{{"value":"","confidence":0}},"預金者名氏名":{{"value":"","confidence":0}},"口座番号":{{"value":"","confidence":0}},"記号番号":{{"value":"","confidence":0}},"銀行番号":{{"value":"","confidence":0}},"支店番号":{{"value":"","confidence":0}},"委託者番号":{{"value":"","confidence":0}},"契約者番号":{{"value":"","confidence":0}}}}"""

    def _parse_response(self, response) -> ClaudeExtractionResult:
        """Step2の応答をパース"""
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
            logger.error(f"Step2 JSONパースに失敗: {e}")
            logger.error(f"応答: {text_response[:500]}")
            raise ValueError(f"Claude応答のJSONパースに失敗: {e}")

        # OcrFieldリスト構築
        extracted_fields = []
        for field_name, field_data in data.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")
                confidence = float(field_data.get("confidence", 90))
            else:
                # フラットJSON形式のフォールバック
                value = field_data
                confidence = 90.0

            confidence_level = (
                ConfidenceLevel.HIGH if confidence >= CONFIDENCE_THRESHOLD
                else ConfidenceLevel.LOW
            )
            extracted_fields.append(OcrField(
                field_name=field_name,
                value=value if value else None,
                confidence_score=confidence,
                confidence_level=confidence_level,
                is_confirmed=False,
                corrected_value=None,
            ))

        needs_review_fields = [
            f.field_name for f in extracted_fields
            if f.confidence_level == ConfidenceLevel.LOW
        ]

        return ClaudeExtractionResult(
            form_type=FormType.GENERAL,
            extracted_fields=extracted_fields,
            needs_review_fields=needs_review_fields,
            deficiency_notes=[],
            correction_suggestions={},
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
