"""
ClaudeClientの単体テスト

モックを使用してAmazon Bedrock Claude APIの呼び出しと
レスポンスパース処理を検証する。
2段階OCR方式（Step1: 全テキスト読取、Step2: 構造化抽出）に対応。
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
        ]
    }).encode("utf-8")
    return {"body": io.BytesIO(body_content)}


def _make_text_response(text: str) -> dict:
    """テキスト応答のinvoke_model戻り値モックを生成"""
    body_content = json.dumps({
        "content": [
            {"type": "text", "text": text}
        ]
    }).encode("utf-8")
    return {"body": io.BytesIO(body_content)}


# === Step2用の標準応答フィクスチャ ===


@pytest.fixture
def step2_response_data():
    """Step2のStructured Outputs準拠JSON応答データ"""
    return {
        "収納代行会社名": {"value": "きらぼしシステム株式会社", "confidence": 92},
        "預金種目": {"value": "普通", "confidence": 95},
        "届出印": {"value": "あり", "confidence": 88},
        "預金者名フリガナ": {"value": "ヤマダ タロウ", "confidence": 85},
        "預金者名氏名": {"value": "山田 太郎", "confidence": 82},
        "口座番号": {"value": "1234567", "confidence": 60},
        "記号番号": {"value": None, "confidence": 50},
        "銀行番号": {"value": "0137", "confidence": 90},
        "支店番号": {"value": "209", "confidence": 88},
        "委託者番号": {"value": "12345", "confidence": 75},
        "契約者番号": {"value": "67890", "confidence": 72},
    }


# === TestParseResponse ===


class TestParseResponse:
    """_parse_responseメソッドのテスト"""

    def test_parse_structured_output_response(self, step2_response_data):
        """Structured Outputs準拠のJSON応答を正しくパースする"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(step2_response_data)
        result = client._parse_response(mock_response)

        assert isinstance(result, ClaudeExtractionResult)
        assert result.form_type == FormType.GENERAL
        assert len(result.extracted_fields) == 11

    def test_parse_confidence_levels(self, step2_response_data):
        """Confidence Levelが閾値70.0で正しく判定される"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(step2_response_data)
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

    def test_parse_needs_review_fields(self, step2_response_data):
        """LOW confidenceのフィールドがneeds_review_fieldsに含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(step2_response_data)
        result = client._parse_response(mock_response)

        # confidence < 70 のフィールド: 口座番号(60), 記号番号(50)
        assert "口座番号" in result.needs_review_fields
        assert "記号番号" in result.needs_review_fields

    def test_parse_null_values(self, step2_response_data):
        """null値のフィールドはvalue=Noneとして処理される"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(step2_response_data)
        result = client._parse_response(mock_response)

        symbol_field = next(
            f for f in result.extracted_fields if f.field_name == "記号番号"
        )
        assert symbol_field.value is None

    def test_parse_fields_are_not_confirmed(self, step2_response_data):
        """パース結果のフィールドはすべて未確認状態"""
        client = ClaudeClient.__new__(ClaudeClient)
        mock_response = _make_invoke_response(step2_response_data)
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


# === TestStep1Prompt ===


class TestStep1Prompt:
    """_step1_promptメソッドのテスト"""

    def test_step1_prompt_contains_instructions(self):
        """Step1プロンプトに読み取り指示が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._step1_prompt()

        assert "預金口座振替依頼書" in prompt
        assert "全ての文字" in prompt
        assert "書き起こし" in prompt

    def test_step1_prompt_mentions_handwriting(self):
        """Step1プロンプトに手書き文字への言及がある"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._step1_prompt()

        assert "手書き" in prompt


# === TestStep2Prompt ===


class TestStep2Prompt:
    """_step2_promptメソッドのテスト"""

    def test_step2_prompt_includes_raw_text(self):
        """Step2プロンプトにStep1のOCRテキストが埋め込まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        raw_text = "テスト用OCRテキスト みずほ銀行 東京営業部"
        prompt = client._step2_prompt(raw_text)

        assert raw_text in prompt

    def test_step2_prompt_includes_field_definitions(self):
        """Step2プロンプトにフィールド定義が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._step2_prompt("テスト")

        assert "収納代行会社名" in prompt
        assert "預金種目" in prompt
        assert "届出印" in prompt
        assert "口座番号" in prompt
        assert "委託者番号" in prompt
        assert "契約者番号" in prompt

    def test_step2_prompt_includes_json_format(self):
        """Step2プロンプトにJSON出力形式の指示が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._step2_prompt("テスト")

        assert "JSON" in prompt
        assert "confidence" in prompt


# === TestOutputSchema ===


class TestOutputSchema:
    """STEP2_OUTPUT_SCHEMAクラス変数のテスト"""

    def test_schema_is_valid_json_schema(self):
        """スキーマがJSON Schema形式として有効"""
        schema = ClaudeClient.STEP2_OUTPUT_SCHEMA

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert schema["additionalProperties"] is False

    def test_schema_has_all_required_fields(self):
        """スキーマに全11フィールドが定義されている"""
        schema = ClaudeClient.STEP2_OUTPUT_SCHEMA
        expected_fields = [
            "収納代行会社名", "預金種目", "届出印", "預金者名フリガナ",
            "預金者名氏名", "口座番号", "記号番号", "銀行番号",
            "支店番号", "委託者番号", "契約者番号",
        ]

        for field in expected_fields:
            assert field in schema["properties"]
            assert field in schema["required"]

    def test_schema_field_structure(self):
        """各フィールドのスキーマ構造が正しい（value + confidence）"""
        schema = ClaudeClient.STEP2_OUTPUT_SCHEMA

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
    def test_two_step_ocr_invokes_model_twice(self, mock_boto3_client, step2_response_data):
        """2段階OCRでinvoke_modelが2回呼ばれる（Step1 + Step2）"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        # Step1: テキスト応答
        step1_response = _make_text_response("口座振替依頼書 みずほ銀行 東京営業部")
        # Step2: JSON応答
        step2_response = _make_invoke_response(step2_response_data)

        mock_bedrock.invoke_model.side_effect = [step1_response, step2_response]

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"\xff\xd8fake_jpeg_data"
        result = asyncio.run(client.extract_fields_from_image(image_bytes))

        # invoke_modelが2回呼ばれたことを確認
        assert mock_bedrock.invoke_model.call_count == 2
        assert isinstance(result, ClaudeExtractionResult)
        assert len(result.extracted_fields) == 11

    @patch("boto3.client")
    def test_image_is_base64_encoded(self, mock_boto3_client, step2_response_data):
        """画像がbase64エンコードされてリクエストに含まれる"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        step1_response = _make_text_response("テスト文書")
        step2_response = _make_invoke_response(step2_response_data)
        mock_bedrock.invoke_model.side_effect = [step1_response, step2_response]

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"\xff\xd8fake_jpeg_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        # Step1のリクエストを検証
        first_call = mock_bedrock.invoke_model.call_args_list[0]
        body = json.loads(first_call[1]["body"])
        content = body["messages"][0]["content"]

        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/jpeg"

        expected_b64 = base64.b64encode(image_bytes).decode("utf-8")
        assert content[0]["source"]["data"] == expected_b64

    @patch("boto3.client")
    def test_step2_includes_output_config(self, mock_boto3_client, step2_response_data):
        """Step2のリクエストにoutput_config（JSON Schema）が含まれる"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        step1_response = _make_text_response("テスト文書")
        step2_response = _make_invoke_response(step2_response_data)
        mock_bedrock.invoke_model.side_effect = [step1_response, step2_response]

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        image_bytes = b"fake_png_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        # Step2のリクエストを検証
        second_call = mock_bedrock.invoke_model.call_args_list[1]
        body = json.loads(second_call[1]["body"])

        # output_configが含まれていることを確認
        assert "output_config" in body
        assert body["output_config"]["format"]["type"] == "json_schema"
        assert body["output_config"]["format"]["schema"] == ClaudeClient.STEP2_OUTPUT_SCHEMA

    @patch("boto3.client")
    def test_png_media_type_detection(self, mock_boto3_client, step2_response_data):
        """JPEG以外の画像はPNGとして処理される"""
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        step1_response = _make_text_response("テスト文書")
        step2_response = _make_invoke_response(step2_response_data)
        mock_bedrock.invoke_model.side_effect = [step1_response, step2_response]

        client = ClaudeClient()
        client.client = mock_bedrock

        import asyncio
        # PNG先頭バイト (0x89 0x50)
        image_bytes = b"\x89PNGfake_png_data"
        asyncio.run(client.extract_fields_from_image(image_bytes))

        first_call = mock_bedrock.invoke_model.call_args_list[0]
        body = json.loads(first_call[1]["body"])
        content = body["messages"][0]["content"]
        assert content[0]["source"]["media_type"] == "image/png"
