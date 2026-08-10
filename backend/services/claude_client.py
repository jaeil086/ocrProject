"""
Amazon Bedrock Claudeクライアント

Claude Sonnet 4を「OCR+文書理解エンジン」として利用する。
1段階OCR方式:
  画像から直接フィールドを構造化抽出（One-shot Prompting + 構造化出力）

パフォーマンス最適化:
  - 2段階→1段階統合により、API呼び出しを1回に削減（処理時間50%短縮）
  - boto3呼び出しをasyncio.to_threadで非同期化（イベントループブロッキング防止）
  - プロンプト簡略化により入力トークン数を削減
"""

import asyncio
import base64
import json
import logging
import time

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
    """Amazon Bedrock Claude — 1段階OCR方式（画像→直接構造化抽出）"""

    # 出力のJSONスキーマ定義
    # Bedrock InvokeModel の output_config で指定し、JSON以外の出力を防止する
    OUTPUT_SCHEMA = {
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
            "お届出印金融機関": {
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
            "ゆうちょ記号": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "ゆうちょ番号": {
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
            "預金者氏名", "預金者フリガナ", "お届出印金融機関", "銀行名", "支店名",
            "預金種目", "口座番号", "銀行番号", "店番号",
            "ゆうちょ記号", "ゆうちょ番号",
            "振替日", "委託者番号", "契約者番号", "委託者名", "料金等の種類"
        ],
        "additionalProperties": False
    }

    # One-shot用の正解例（実際の帳票から期待される出力）
    # 銀行番号がnullの例を含め、空欄フィールドの正しい処理を示す
    ONE_SHOT_EXAMPLE_OUTPUT = json.dumps({
        "預金者氏名": {"value": "小川 敦大", "confidence": 90},
        "預金者フリガナ": {"value": "オガワ アツヒロ", "confidence": 92},
        "お届出印金融機関": {"value": "あり", "confidence": 85},
        "銀行名": {"value": "三井住友（銀行）", "confidence": 95},
        "支店名": {"value": "国領", "confidence": 93},
        "預金種目": {"value": "普通", "confidence": 95},
        "口座番号": {"value": "6667221", "confidence": 88},
        "銀行番号": {"value": None, "confidence": 0},
        "店番号": {"value": "681", "confidence": 90},
        "ゆうちょ記号": {"value": None, "confidence": 0},
        "ゆうちょ番号": {"value": None, "confidence": 0},
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
        1段階OCR: 画像から直接構造化フィールドを抽出

        従来の2段階方式（Step1:全テキストOCR → Step2:構造化抽出）を
        1回のAPI呼び出しに統合し、処理時間を約50%短縮。
        """
        t_start = time.perf_counter()

        result = await self._extract_fields(image_bytes)

        elapsed = time.perf_counter() - t_start
        logger.info(f"Claude API呼び出し完了: {elapsed:.2f}秒")

        return result

    @retry(
        stop=stop_after_attempt(BEDROCK_MAX_RETRIES),
        wait=wait_exponential(min=BEDROCK_RETRY_MIN_WAIT, max=BEDROCK_RETRY_MAX_WAIT),
    )
    async def _extract_fields(
        self, image_bytes: bytes
    ) -> ClaudeExtractionResult:
        """
        画像から直接フィールドを構造化抽出（One-shot + 構造化出力）
        boto3呼び出しをasyncio.to_threadで非同期実行し、イベントループをブロックしない。
        """
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        media_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": CLAUDE_MAX_TOKENS,
            "messages": [
                # One-shot例: ユーザー入力（画像の代わりにテキスト説明）
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._system_prompt()
                                + "\n\n以下は預金口座振替依頼書の画像です。フィールドを抽出してください。",
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
                # 実際のリクエスト（画像付き）
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
                            "text": "この預金口座振替依頼書の画像からフィールドを抽出してください。"
                                "マス目の数字は1マスずつ左から右へ正確に読み取ってください。"
                                "マス目が空欄（何も書かれていない）の場合はnullを返してください。"
                                "他のフィールドの情報から推測して値を埋めることは禁止です。",
                        },
                    ],
                },
            ],
            # 構造化出力: JSON Schemaを指定し、JSON以外の出力を防止
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": self.OUTPUT_SCHEMA,
                }
            },
        }

        logger.info(
            f"Claude APIリクエスト: modelId={BEDROCK_INFERENCE_PROFILE_ID}, "
            f"画像サイズ={len(image_bytes)/1024:.0f}KB, "
            f"media_type={media_type}"
        )

        # boto3はsynchronousなので、to_threadで非同期実行
        response = await asyncio.to_thread(
            self.client.invoke_model,
            modelId=BEDROCK_INFERENCE_PROFILE_ID,
            body=json.dumps(request_body),
        )

        return self._parse_response(response)

    def _system_prompt(self) -> str:
        """画像から直接フィールドを抽出するプロンプト"""
        return """あなたは日本の金融帳票OCRエンジンです。
「預金口座振替依頼書」の画像から、以下のフィールドを正確に抽出してください。

【抽出フィールド】
1. 預金者氏名: 「氏名」欄の名前（法人の場合は法人名含む）
2. 預金者フリガナ: 「フリガナ」欄のカタカナ（見えるまま、補正禁止）
3. お届出印金融機関: 届出印（金融機関届出印）の押印欄に印影があるかどうか。印影が見える場合は"あり"、見えない場合は"なし"を返す。
4. 銀行名: 金融機関名（手書きまたはスタンプ）＋右側の種別選択を括弧付きで付加する。
   右側には縦に「銀行」「信用金庫」「組合」の3つが印刷されており、その中の1つに丸印が付いている。
   括弧内に入れる値は必ず以下の3つのいずれかのみ:
     - "銀行"
     - "信用金庫"
     - "組合"
   これ以外の文字列（例: "信用組合"）を括弧内に入れてはならない。
   例: 手書き欄に「三井住友」、右側で「銀行」に丸 → "三井住友（銀行）"
   例: 手書き欄に「城南」、右側で「信用金庫」に丸 → "城南（信用金庫）"
   例: 手書き欄に「えがみ」、右側で「組合」に丸 → "えがみ（組合）"
   ※ 丸印がどれにも付いていない場合は金融機関名に「（x）」を付けて返す。
   例: 手書き欄に「きらぼし」、右側でどれにも丸なし → "きらぼし（x）"
5. 支店名: 支店名（手書きまたはスタンプ）
6. 預金種目: 「1.普通」「2.当座」の選択された種目名
7. 口座番号: マス目の7桁数字（左→右、1マス=1桁）
8. 銀行番号: 金融機関コード4桁（先頭0含む、例: "0137"）。マス目が空欄ならnull。
9. 店番号: 支店コード3桁（先頭0含む、例: "207"）。マス目が空欄ならnull。
10. ゆうちょ記号: 「※ゆうちょ銀行ご利用の場合」欄の「記号」フィールド（5桁数字）。
    契約種別コードの右側にある5桁の数字。マス目が空欄ならnull。
11. ゆうちょ番号: 「※ゆうちょ銀行ご利用の場合」欄の「番号」フィールド（最大8桁数字）。
    記号の右側にある数字。マス目が空欄ならnull。
12. 振替日: 12日・27日のうち〇が付いた方の数字のみ（例: "27"）
13. 委託者番号: 下部マス目の前半5桁
14. 契約者番号: 同マス目の後半5桁
15. 委託者名: 下部「委託者名」欄の会社名
16. 料金等の種類: 「料金等の種類」欄の内容

【銀行情報の読み取り方針】
★ この帳票には「※ゆうちょ銀行以外の金融機関ご利用の場合」と「※ゆうちょ銀行ご利用の場合」の2つの欄がある。
★ どちらか一方に記入がある（稀に両方に一部記入がある場合もある）。
★ 「ゆうちょ銀行以外」欄に記入がある場合: 銀行名・支店名・預金種目・口座番号・銀行番号・店番号を抽出。ゆうちょ記号・ゆうちょ番号はnull。
★ 「ゆうちょ銀行」欄に記入がある場合: ゆうちょ記号・ゆうちょ番号を抽出。銀行名・支店名・預金種目・口座番号・銀行番号・店番号はnull。
★ 両方に記入がある場合: 見えるものをすべて抽出する。

【最重要ルール — 空欄判定】
★ マス目・記入欄に何も書かれていない場合は、必ず null を返すこと。
★ 他のフィールドの情報から推測・補完してはならない。
  例: 銀行名が「みずほ銀行」でも、銀行番号のマス目が空欄なら銀行番号はnull。
  例: 支店名が分かっても、店番号のマス目が空欄なら店番号はnull。
★ 「画像に文字が見える」場合のみ値を返す。知識で埋めることは厳禁。

【読み取りルール】
- マス目の数字: 左端から右端まで1マスずつ順番に読む。桁を飛ばさない。
- 手書き文字: 見えるままを返す。推測・補正・修正は禁止。
- フリガナ: 不自然でもよくある人名に置き換えない。
- 手書き数字判別: 0=楕円閉じた形、1=縦直線、6=下に丸い膨らみ、9=上に丸い膨らみ。
- 空欄のマス目: 何も書かれていなければ null を返す。知識による推測は厳禁。"""

    def _parse_response(self, response) -> ClaudeExtractionResult:
        """
        応答をパース

        output_config.json_schema指定により、応答は純粋なJSON文字列のみ。
        コードブロックや説明文が混ざることはないため、直接json.loadsでパース可能。
        """
        response_body = json.loads(response["body"].read())

        # パフォーマンスログ
        usage = response_body.get("usage", {})
        logger.info(
            f"Claude応答: model={response_body.get('model')}, "
            f"stop_reason={response_body.get('stop_reason')}, "
            f"input_tokens={usage.get('input_tokens', '?')}, "
            f"output_tokens={usage.get('output_tokens', '?')}"
        )

        content = response_body.get("content", [])
        text_response = ""
        for block in content:
            if block.get("type") == "text":
                text_response = block.get("text", "")
                break

        try:
            # 構造化出力により応答は純粋なJSON — 直接パース
            data = json.loads(text_response)
        except json.JSONDecodeError as e:
            logger.error(f"JSONパースに失敗: {e}")
            logger.error(f"応答: {text_response[:500]}")
            raise ValueError(f"Claude応答のJSONパースに失敗: {e}")

        # OcrFieldリスト構築
        extracted_fields = []
        for field_name, field_data in data.items():
            value = field_data.get("value")
            confidence = float(field_data.get("confidence", 90))

            # 値がnull（空欄）の場合はconfidence判定不要（空欄は正常なのでHIGH扱い）
            if not value:
                confidence_level = ConfidenceLevel.HIGH
            else:
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
