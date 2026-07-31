"""
Amazon Bedrock Claudeクライアント

Claude Sonnet 4.5を「OCR+文書理解エンジン」として利用する。
2段階OCR方式:
  Step1: 画像内の全テキストを読み取り
  Step2: 読み取りテキストからフィールドを構造化抽出
"""



"""
!Invoke API

client = boto3.client('bedrock-runtime', region_name='ap-northeast-1')
response = client.invoke_model( 
    modelId='anthropic.claude-sonnet-4-5-20250929-v1:0', 
    body=json.dumps({ 
            'anthropic_version': 'bedrock-2023-05-31', 
            'messages': [{ 'role': 'user', 'content': 'Can you explain the features 
 of Amazon Bedrock?'}], 
            'max_tokens': 1024 
    })
)
print(json.loads(response['body'].read()))


!Converse API

client = boto3.client('bedrock-runtime', region_name='ap-northeast-1')
response = client.converse( 
    modelId='anthropic.claude-sonnet-4-5-20250929-v1:0', 
    messages=[ 
        { 
            'role': 'user', 
            'content': [{'text': 'Can you explain the features of Amazon Bedrock?'}] 
        } 
    ]
)
print(response)
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

    # Step2出力のJSONスキーマ定義
    # Structured Outputsにより、JSON以外の余計なテキストが混ざらなくなる
    STEP2_OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "収納代行会社名": {
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
            "届出印": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "預金者名フリガナ": {
                "type": "object",
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "integer"}
                },
                "required": ["value", "confidence"],
                "additionalProperties": False
            },
            "預金者名氏名": {
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
            "記号番号": {
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
            "支店番号": {
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
            }
        },
        "required": [
            "収納代行会社名", "預金種目", "届出印", "預金者名フリガナ",
            "預金者名氏名", "口座番号", "記号番号", "銀行番号",
            "支店番号", "委託者番号", "契約者番号"
        ],
        "additionalProperties": False
    }

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

        request_body = {
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
            # Structured Outputs: JSON Schemaを指定し、JSON以外の出力を防止
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": self.STEP2_OUTPUT_SCHEMA,
                }
            },
        }

        # デバッグログ: output_configが含まれていることを確認
        logger.info(
            f"Step2リクエスト: modelId={BEDROCK_INFERENCE_PROFILE_ID}, "
            f"output_config含む={('output_config' in request_body)}, "
            f"schema_type={request_body['output_config']['format']['type']}"
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

読み取れた文字をそのまま出力してください。
特に数字マス目は「左から右、1マス=1桁」を厳守してください。"""

    def _step2_prompt(self, raw_text: str) -> str:
        """Step2: フィールド抽出プロンプト"""
        return f"""あなたは日本の金融帳票OCRエンジンです。
下記は画像から読み取ったテキストです。画像も参照しながら、各フィールドの値を抽出してください。

【読み取りテキスト】
{raw_text}

【最重要ルール — 絶対に守ること】
★ 数字フィールド（口座番号・銀行番号・支店番号・委託者番号・契約者番号）は
  必ず画像のマス目を直接確認して1マスずつ読み取ること。
  読み取りテキスト(Step1結果)と画像が矛盾する場合、画像のマス目を優先すること。
★ マス目の読み取り手順:
  (1) マス目の左端を見つける
  (2) 左から右へ1マスずつ、各マス内の数字を1桁として読む
  (3) 桁の入れ替え・スキップは絶対にしない
★ 手書き文字は画像に見えるままを返すこと。推測・補正・修正は一切禁止。
★ フリガナが不自然な名前に見えても、よくある人名に置き換えてはいけない。
  例: 画像に「アツフロ」と書いてあれば「アツフロ」と返す。「ヒロキ」等に補正しない。
★ 手書き数字の判別基準:
  - 「0」(ゼロ): 楕円形の閉じた形。内部が空洞。上下に開きがない。
  - 「1」(イチ): 縦の直線のみ。上部にセリフ（短い横棒）がある場合もあるが基本は棒1本。
  - 「6」(ロク): 下半分に丸い膨らみがある。上部は左に巻く曲線。
  - 「9」(ナイン): 上半分に丸い膨らみがある。下部に直線が伸びる。
  - 「0」と「6」: 0は左右対称で完全に閉じている。6は上部が開いており非対称。
  - 「0」と「9」: 0は上下対称。9は上部が丸く下部が細い線。

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
   ※ 不自然に見えても補正しない。画像の文字をそのまま返すこと。
   ※ 1マスに1文字ずつ書かれている場合、左から順番に連結する。

5. 預金者名氏名:
   「氏名」欄に記入されている名前をそのまま返す。法人の場合は法人名・肩書・代表者名を含む。空欄なら null。
   ※ 手書き文字が読みにくくても、見えるままを返す。推測で修正しない。

6. 口座番号:
   「口座番号」欄（ゆうちょ以外）に記入されている7桁の数字をそのまま返す。
   ※ 口座番号は必ず7桁です。7桁で返してください。空欄なら null。
   ※ 画像のマス目を左端から右端まで1マスずつ確認すること。
   ※ Step1テキストと画像が異なる場合、画像を優先。
   ※ 各マスの数字をそのまま連結する。桁を入れ替えない。

7. 記号番号:
   「※ゆうちょ銀行ご利用の場合」セクションの記号・番号欄に手書き記入された数字。空欄なら null。
   ※ 印刷済みの「00100-3-578806」等の加入者番号とは異なるので注意。

8. 銀行番号:
   「※ゆうちょ銀行以外の金融機関ご利用の場合」セクション内、金融機関名の下にある「コード」欄の4桁数字。
   先頭0を省略せず4桁で返す（例: "0137"）。
   ※ 画像のマス目を左端から右端まで1マスずつ確認すること。
   ※ Step1テキストと画像が異なる場合、画像を優先。
   ※ 特に「0」と「1」の混同に注意: 0は丸い楕円、1は縦棒のみ。

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
confidenceは「画像から明確に読み取れた確信度」であり、補正後の確信度ではない。

{{"収納代行会社名":{{"value":"","confidence":0}},"預金種目":{{"value":"","confidence":0}},"届出印":{{"value":"","confidence":0}},"預金者名フリガナ":{{"value":"","confidence":0}},"預金者名氏名":{{"value":"","confidence":0}},"口座番号":{{"value":"","confidence":0}},"記号番号":{{"value":"","confidence":0}},"銀行番号":{{"value":"","confidence":0}},"支店番号":{{"value":"","confidence":0}},"委託者番号":{{"value":"","confidence":0}},"契約者番号":{{"value":"","confidence":0}}}}"""

    def _parse_response(self, response) -> ClaudeExtractionResult:
        """
        Step2の応答をパース

        output_config.json_schema指定により、応答は純粋なJSON文字列のみ。
        コードブロックや説明文が混ざることはないため、直接json.loadsでパース可能。
        """
        response_body = json.loads(response["body"].read())

        # デバッグログ: レスポンス原文を出力（画像データ除く）
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

        # デバッグログ: 応答テキスト（先頭500文字）
        logger.info(f"Step2応答テキスト（先頭500文字）: {text_response[:500]}")

        try:
            # Structured Outputsにより応答は純粋なJSON — 直接パース
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
