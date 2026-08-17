"""
ClaudeClientの単体テスト

モックを使用してAmazon Bedrock Claude APIの呼び出しと
レスポンスパース処理を検証する。
1段階OCR方式（画像→直接構造化抽出）に対応。
"""

import base64
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.models.enums import ConfidenceLevel, FormType
from backend.models.schemas import ClaudeExtractionResult
from backend.services.claude_client import ClaudeClient


# === ヘルパー関数 ===


def _make_invoke_response(response_dict: dict) -> dict:
    """invoke_model戻り値のモックを生成"""
    body_content = json.dumps({
        "content": [
            {"type": "text", "text": json.dumps(response_dict, ensure_ascii=False)}
        ],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }).encode("utf-8")
    return {"body": io.BytesIO(body_content)}


def _make_text_response(text: str) -> dict:
    """テキスト応答のinvoke_model戻り値モックを生成"""
    body_content = json.dumps({
        "content": [
            {"type": "text", "text": text}
        ],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 500, "output_tokens": 100},
    }).encode("utf-8")
    return {"body": io.BytesIO(body_content)}


# === 標準応答フィクスチャ ===


@pytest.fixture
def extraction_response_data():
    """構造化出力準拠JSON応答データ"""
    return {
        "預金者氏名": {"value": "山田 太郎", "confidence": 82},
        "預金者フリガナ": {"value": "ヤマダ タロウ", "confidence": 85},
        "銀行名": {"value": "みずほ銀行", "confidence": 92},
        "支店名": {"value": "東京営業部", "confidence": 88},
        "預金種目": {"value": "普通", "confidence": 95},
        "口座番号": {"value": "1234567", "confidence": 60},
        "銀行番号": {"value": "0137", "confidence": 90},
        "店番号": {"value": "209", "confidence": 88},
        "振替日": {"value": "27", "confidence": 92},
        "委託者番号": {"value": "12345", "confidence": 75},
        "契約者番号": {"value": "67890", "confidence": 72},
        "委託者名": {"value": "テスト株式会社", "confidence": 90},
        "料金等の種類": {"value": "ご利用料", "confidence": 50},
    }


# === TestParseResponse ===


class TestParseResponse:
    """_parse_responseメソッドのテスト"""

    def test_parse_structured_output_response(self, extraction_response_data):
        """構造化出力準拠のJSON応答を正しくパースする"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(extraction_response_data)
        result = client._parse_response(mock_response)

        assert isinstance(result, ClaudeExtractionResult)
        assert result.form_type == FormType.GENERAL
        assert len(result.extracted_fields) == 13

    def test_parse_confidence_levels(self, extraction_response_data):
        """Confidence Levelが閾値70.0で正しく判定される"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(extraction_response_data)
        result = client._parse_response(mock_response)

        # 預金種目: 95 >= 70.0 → HIGH
        deposit_field = next(
            f for f in result.extracted_fields if f.field_name == "預金種目"
        )
        assert deposit_field.confidence_level == ConfidenceLevel.HIGH
        assert deposit_field.confidence_score == 95.0

        # 口座番号: 60 < 70.0 → LOW
        account_field = next(
            f for f in result.extracted_fields if f.field_name == "口座番号"
        )
        assert account_field.confidence_level == ConfidenceLevel.LOW
        assert account_field.confidence_score == 60.0

    def test_parse_needs_review_fields(self, extraction_response_data):
        """LOW confidenceのフィールドがneeds_review_fieldsに含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(extraction_response_data)
        result = client._parse_response(mock_response)

        # confidence < 70 のフィールド: 口座番号(60), 料金等の種類(50)
        assert "口座番号" in result.needs_review_fields
        assert "料金等の種類" in result.needs_review_fields

    def test_parse_null_values(self, extraction_response_data):
        """null値のフィールドはvalue=Noneとして処理される"""
        extraction_response_data["銀行名"] = {"value": None, "confidence": 50}
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(extraction_response_data)
        result = client._parse_response(mock_response)

        bank_field = next(
            f for f in result.extracted_fields if f.field_name == "銀行名"
        )
        assert bank_field.value is None

    def test_parse_fields_are_not_confirmed(self, extraction_response_data):
        """パース結果のフィールドはすべて未確認状態"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(extraction_response_data)
        result = client._parse_response(mock_response)

        for field in result.extracted_fields:
            assert field.is_confirmed is False
            assert field.corrected_value is None

    def test_parse_invalid_json_raises_error(self):
        """不正なJSON応答でValueErrorが発生する"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_text_response("これはJSONではありません")

        with pytest.raises(ValueError, match="JSONパースに失敗"):
            client._parse_response(mock_response)


# === TestSystemPrompt ===


class TestSystemPrompt:
    """_system_promptメソッドのテスト"""

    def test_system_prompt_contains_instructions(self):
        """システムプロンプトに読み取り指示が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._system_prompt()

        assert "預金口座振替依頼書" in prompt
        assert "抽出" in prompt

    def test_system_prompt_mentions_handwriting(self):
        """システムプロンプトに手書き文字への言及がある"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._system_prompt()

        assert "手書き" in prompt

    def test_system_prompt_includes_field_definitions(self):
        """システムプロンプトにフィールド定義が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._system_prompt()

        assert "預金者氏名" in prompt
        assert "預金者フリガナ" in prompt
        assert "銀行名" in prompt
        assert "支店名" in prompt
        assert "預金種目" in prompt
        assert "口座番号" in prompt
        assert "委託者番号" in prompt
        assert "契約者番号" in prompt
        assert "委託者名" in prompt
        assert "料金等の種類" in prompt


# === TestOutputSchema ===


class TestOutputSchema:
    """OUTPUT_SCHEMAクラス変数のテスト"""

    def test_schema_is_valid_json_schema(self):
        """スキーマがJSON Schema形式として有効"""
        schema = ClaudeClient.OUTPUT_SCHEMA

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert schema["additionalProperties"] is False

    def test_schema_has_all_required_fields(self):
        """スキーマに全13フィールドが定義されている"""
        schema = ClaudeClient.OUTPUT_SCHEMA
        expected_fields = [
            "預金者氏名", "預金者フリガナ", "銀行名", "支店名",
            "預金種目", "口座番号", "銀行番号", "店番号",
            "振替日", "委託者番号", "契約者番号", "委託者名", "料金等の種類",
        ]

        for field in expected_fields:
            assert field in schema["properties"]
            assert field in schema["required"]

    def test_schema_field_structure(self):
        """各フィールドのスキーマ構造が正しい（value + confidence）"""
        schema = ClaudeClient.OUTPUT_SCHEMA

        for field_name, field_schema in schema["properties"].items():
            assert field_schema["type"] == "object"
            assert "value" in field_schema["properties"]
            assert "confidence" in field_schema["properties"]
            assert field_schema["properties"]["confidence"]["type"] == "integer"
            assert field_schema["additionalProperties"] is False


# === TestExtractFieldsFromImage（統合テスト） ===


class TestExtractFieldsFromImage:
    """extract_fields_from_imageメソッドのテスト"""

    @patch("boto3.client")
    def test_single_step_ocr_invokes_model_once(self, mock_boto3_client, extraction_response_data):
        """1段階OCRでinvoke_modelが1回だけ呼ばれる"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        # 1回のJSON応答
        response = _make_invoke_response(extraction_response_data)
        mock_bedrock.invoke_model.return_value = response

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"\xff\xd8fake_jpeg_data"
        result = asyncio.run(client.extract_fields_from_image(image_bytes))

        # invoke_modelが1回だけ呼ばれたことを確認
        assert mock_bedrock.invoke_model.call_count == 1
        assert isinstance(result, ClaudeExtractionResult)
        assert len(result.extracted_fields) == 13

    @patch("boto3.client")
    def test_image_is_base64_encoded(self, mock_boto3_client, extraction_response_data):
        """画像がbase64エンコードされてリクエストに含まれる"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        response = _make_invoke_response(extraction_response_data)
        mock_bedrock.invoke_model.return_value = response

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"\xff\xd8fake_jpeg_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        # リクエストを検証
        call_args = mock_bedrock.invoke_model.call_args
        body = json.loads(call_args[1]["body"])
        # 実際のリクエスト（3番目のメッセージ）に画像が含まれる
        actual_message = body["messages"][2]
        content = actual_message["content"]

        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/jpeg"

        expected_b64 = base64.b64encode(image_bytes).decode("utf-8")
        assert content[0]["source"]["data"] == expected_b64

    @patch("boto3.client")
    def test_request_includes_output_config(self, mock_boto3_client, extraction_response_data):
        """リクエストにoutput_config（JSON Schema）が含まれる"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        response = _make_invoke_response(extraction_response_data)
        mock_bedrock.invoke_model.return_value = response

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"fake_png_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        # リクエストを検証
        call_args = mock_bedrock.invoke_model.call_args
        body = json.loads(call_args[1]["body"])

        # output_configが含まれていることを確認
        assert "output_config" in body
        assert body["output_config"]["format"]["type"] == "json_schema"
        assert body["output_config"]["format"]["schema"] == ClaudeClient.OUTPUT_SCHEMA

    @patch("boto3.client")
    def test_png_media_type_detection(self, mock_boto3_client, extraction_response_data):
        """JPEG以外の画像はPNGとして処理される"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        response = _make_invoke_response(extraction_response_data)
        mock_bedrock.invoke_model.return_value = response

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        # PNG先頭バイト (0x89 0x50)
        image_bytes = b"\x89PNGfake_png_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        call_args = mock_bedrock.invoke_model.call_args
        body = json.loads(call_args[1]["body"])
        actual_message = body["messages"][2]
        content = actual_message["content"]
        assert content[0]["source"]["media_type"] == "image/png"

    @patch("boto3.client")
    def test_one_shot_example_in_request(self, mock_boto3_client, extraction_response_data):
        """リクエストにOne-shot例が含まれている"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        response = _make_invoke_response(extraction_response_data)
        mock_bedrock.invoke_model.return_value = response

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"\xff\xd8fake_jpeg_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        call_args = mock_bedrock.invoke_model.call_args
        body = json.loads(call_args[1]["body"])

        # 3メッセージ: One-shot user, One-shot assistant, 実リクエスト
        assert len(body["messages"]) == 3
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][2]["role"] == "user"
