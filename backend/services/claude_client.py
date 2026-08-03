"""
Amazon Bedrock Claudeクライアント

Claude Sonnet 4を「OCR+文書理解エンジン」として利用する。
2段階OCR方式:
  Step1: 画像内の全テキストを読み取り
  Step2: 読み取りテキストからフィールドを構造化抽出（One-shot Prompting + 構造化出力）
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
    """Amazon Bedrock Claude — 2段階OCR方式（One-shot Prompting + 構造化出力）"""

    # Step2出力のJSONスキーマ定義
    # Bedrock InvokeModel の output_config で指定し、JSON以外の出力を防止する
    STEP2_OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "預金者氏名": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "預金者フリガナ": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "銀行名": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "支店名": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "預金種目": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "口座番号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "銀行番号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "店番号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "振替日": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "委託者番号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "契約者番号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "委託者名": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "料金等の種類": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            }
        },
        "required": [
            "預金者氏名", "預金者フリガナ", "銀行名", "支店名",
            "預金種目", "口座番号", "銀行番号", "店番号",
            "振替日", "委託者番号", "契約者番号", "委託者名", "料金等の種類"
        ],
        "additionalProperties": False
    }

    # One-shot用の正解例（実際の帳票から期待される出力）
    ONE_SHOT_EXAMPLE_INPUT = """画像は「預金口座振替依頼書」で、以下のテキストが読み取られました:

株式会社 きらぼし銀行 御中
収納代行会社名 1 きらぼしシステム株式会社 2 三菱UFJファクター株式会社
フリガナ オガワ ヨシヒロ
氏名 小川 敦大
※ゆうちょ銀行以外の金融機関ご利用の場合
三井住友銀行 国領 コード 0 0 1 9 支店 店番号 6 8 1
預金種目 1.普通 2.当座  口座番号 4 6 0 7 2 1 2
※ゆうちょ銀行ご利用の場合
記号番号 3 0  払込先 口座番号 00100-3-578806 加入者 きらぼしシステム株式会社
開始年月 2026年 9月  振替日 12日・27日
委託者番号・契約者番号 1 1 1 3 7 1 0 1 1 6
委託者名 ニクークス 株式会社  料金等の種類 ご利用料"""

    ONE_SHOT_EXAMPLE_OUTPUT = json.dumps({
        "預金者氏名": {"value": "小川 敦大", "confidence": 90},
        "預金者フリガナ": {"value": "オガワ ヨシヒロ", "confidence": 92},
        "銀行名": {"value": "三井住友銀行", "confidence": 95},
        "支店名": {"value": "国領", "confidence": 93},
        "預金種目": {"value": "普通", "confidence": 95},
        "口座番号": {"value": "4607212", "confidence": 88},
        "銀行番号": {"value": "0019", "confidence": 90},
        "店番号": {"value": "681", "confidence": 90},
        "振替日": {"value": "27", "confidence": 92},
        "委託者番号": {"value": "11137", "confidence": 95},
        "契約者番号": {"value": "10116", "confidence": 88},
        "委託者名": {"value": "ニクークス株式会社", "confidence": 93},
        "料金等の種類": {"value": "ご利用料", "confidence": 94}
    }, ensure_ascii=False)

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
        Step2: テキストから構造化フィールドを抽出（One-shot + 構造化出力）
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
        """
        Step2: OCRテキスト+画像からフィールドを構造化抽出
        One-shot Prompting + Bedrock構造化出力を使用
        """
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        media_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": CLAUDE_MAX_TOKENS,
            "messages": [
                # One-shot例: ユーザー入力
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._step2_system_prompt() + "\n\n【入力テキスト】\n" + self.ONE_SHOT_EXAMPLE_INPUT,
                        },
                    ],
                },
                # One-shot例: アシスタント出力
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": self.ONE_SHOT_EXAMPLE_OUTPUT,
                        },
                    ],
                },
                # 実際のリクエスト
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
                            "text": self._step2_user_prompt(raw_text),
                        },
                    ],
                },
            ],
            # 構造化出力: JSON Schemaを指定し、JSON以外の出力を防止
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": self.STEP2_OUTPUT_SCHEMA,
                }
            },
        }

        # デバッグログ
        logger.info(
            f"Step2リクエスト: modelId={BEDROCK_INFERENCE_PROFILE_ID}, "
            f"output_config含む={('output_config' in request_body)}, "
            f"schema_type={request_body['output_config']['format']['type']}, "
            f"messages数={len(request_body['messages'])} (One-shot含む)"
        )

        response = self.client.invoke_model(
            modelId=BEDROCK_INFERENCE_PROFILE_ID,
            body=json.dumps(request_body),
        )

        return self._parse_response(response)

    def _step1_prompt(self) -> str:
        """Step1: 全テキスト読み取りプロンプト"""
        return """この画像は日本の「預金口座振替依頼書」です。
画像内に書かれている全ての文字（印字・手書き・スタンプ含む）を、
上から下、左から右の順序でそのまま書き起こしてください。

【重要な読み取りルール】
1. マス目に1文字ずつ書かれている数字は、1マスずつ区切って正確に読み取ること。
   マスの境界線を基準に各セルの中心にある文字を1つずつ認識すること。
   ※ 必ず左端のマスから右端のマスまで順番通りに読むこと。桁を飛ばしたり入れ替えたりしない。
2. 手書き文字は見えるままに書き起こすこと。推測で修正・補正しないこと。
3. フリガナ欄のカタカナは1文字ずつ正確に読み取ること。
   よくある人名に補正してはいけない。見えるままのカタカナをそのまま返す。
4. 口座番号・銀行番号（コード）・店番号のマス目は、各マスに1桁ずつ数字が入っている。
   マス目の線を基準にして、左から右へ1桁ずつ順番に読み取ること。
5. 手書き数字の判別ルール:
   - 「0」(ゼロ): 楕円形の閉じた丸い形。内部が空洞。
   - 「9」(ナイン): 上部に小さい丸、下部に直線が伸びる。
   - 「6」(ロク): 下部に丸い膨らみ、上部に曲線が伸びる。
   - 「1」(イチ): 縦の直線のみ。横棒がない。
   - 「7」(ナナ): 上部に横棒、そこから斜め下に線が伸びる。
   - 「2」(ニ): 上部にカーブ、底部に横棒。
   - 上記の特徴を見比べ、マスの中の実際の線の形状で判断すること。
6. 金融機関名・支店名は印字またはスタンプであることが多い。正確に読み取ること。
7. 「委託者名」「料金等の種類」欄も正確に読み取ること。

読み取れた文字をそのまま出力してください。
特に数字マス目は「左から右、1マス=1桁」を厳守してください。"""

    def _step2_system_prompt(self) -> str:
        """Step2: システムプロンプト（One-shotの前に1回だけ出す抽出ルール）"""
        return """あなたは日本の金融帳票OCRエンジンです。
「預金口座振替依頼書」の画像と読み取りテキストから、以下のフィールドを正確に抽出してください。

【抽出フィールド一覧】
1. 預金者氏名: 「氏名」欄に記入されている名前。法人の場合は法人名・肩書含む。
2. 預金者フリガナ: 「フリガナ」欄のカタカナ。画像の文字そのままを返す。補正禁止。
3. 銀行名: 「※ゆうちょ銀行以外の金融機関ご利用の場合」の金融機関名（手書きまたはスタンプ）。
4. 支店名: 同セクションの支店名（手書きまたはスタンプ）。
5. 預金種目: 「1.普通」「2.当座」のどちらが選択されているか。選択された種目名を返す。
6. 口座番号: マス目の7桁数字。左端から右端まで1マスずつ読む。必ず7桁で返す。
7. 銀行番号: 金融機関コード。4桁数字。先頭0含む（例: "0137"）。
8. 店番号: 支店コード。3桁数字。先頭0含む（例: "207"）。
9. 振替日: 「振替日」欄の日付。12日・27日のうち〇が付いた方の数字のみ返す（例: "27"）。
10. 委託者番号: 帳票下部「委託者番号・契約者番号」マス目の前半5桁。
11. 契約者番号: 同マス目の後半5桁。
12. 委託者名: 帳票下部「委託者名」欄の会社名。
13. 料金等の種類: 「料金等の種類」欄の内容。

【最重要ルール】
★ 数字フィールド（口座番号・銀行番号・店番号・委託者番号・契約者番号）は
  必ず画像のマス目を直接確認して1マスずつ読み取ること。
★ 手書き文字は画像に見えるままを返す。推測・補正・修正は一切禁止。
★ フリガナが不自然に見えても、よくある人名に置き換えない。
★ 手書き数字の判別基準:
  - 「0」: 楕円形の閉じた形。内部が空洞。
  - 「1」: 縦の直線のみ。
  - 「6」: 下半分に丸い膨らみ。上部は左に巻く曲線。
  - 「9」: 上半分に丸い膨らみ。下部に直線が伸びる。
★ Step1テキストと画像のマス目が矛盾する場合、画像を優先。"""

    def _step2_user_prompt(self, raw_text: str) -> str:
        """Step2: 実際のリクエスト用ユーザープロンプト"""
        return f"""上記のルールに従い、この画像と読み取りテキストからフィールドを抽出してください。

【読み取りテキスト（Step1結果）】
{raw_text}

画像のマス目を直接確認し、正確に抽出してください。"""

    def _parse_response(self, response) -> ClaudeExtractionResult:
        """
        Step2の応答をパース

        output_config.json_schema指定により、応答は純粋なJSON文字列のみ。
        コードブロックや説明文が混ざることはないため、直接json.loadsでパース可能。
        """
        response_body = json.loads(response["body"].read())

        # デバッグログ
        logger.info(
            f"Step2レスポンス: model={response_body.get('model')}, "
            f"stop_reason={response_body.get('stop_reason')}, "
            f"usage={response_body.get('usage')}"
        )

        content = response_body.get("content", [])
        text_response = ""
        for block in content:
            if block.get("type") == "text":
                text_response = block.get("text", "")
                break

        # デバッグログ
        logger.info(f"Step2応答テキスト（先頭500文字）: {text_response[:500]}")

        try:
            # 構造化出力により応答は純粋なJSON — 直接パース
            data = json.loads(text_response)
        except json.JSONDecodeError as e:
            logger.error(f"Step2 JSONパースに失敗: {e}")
            logger.error(f"応答: {text_response[:500]}")
            raise ValueError(f"Claude応答のJSONパースに失敗: {e}")

        # OcrFieldリスト構築
        extracted_fields = []
        for field_name, field_data in data.items():
            value = field_data.get("value")
            confidence = float(field_data.get("confidence", 90))

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
