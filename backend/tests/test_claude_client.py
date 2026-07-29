"""
ClaudeClientの単体テスト

モックを使用してAmazon Bedrock Claude APIの呼び出しと
レスポンスパース処理を検証する。
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.models.enums import ConfidenceLevel, FormType
from backend.models.schemas import ClaudeExtractionResult, TextractLine, TextractResult, TextractWord
from backend.services.claude_client import ClaudeClient


@pytest.fixture
def sample_textract_result() -> TextractResult:
    """テスト用Textract結果"""
    return TextractResult(
        lines=[
            TextractLine(
                text="口座振替依頼書",
                confidence=95.0,
                words=[TextractWord(text="口座振替依頼書", confidence=95.0, bounding_box={"Left": 0.1, "Top": 0.1, "Width": 0.3, "Height": 0.05})],
            ),
            TextractLine(
                text="みずほ銀行",
                confidence=88.5,
                words=[TextractWord(text="みずほ銀行", confidence=88.5, bounding_box={"Left": 0.1, "Top": 0.2, "Width": 0.2, "Height": 0.05})],
            ),
            TextractLine(
                text="東京営業部",
                confidence=72.3,
                words=[TextractWord(text="東京営業部", confidence=72.3, bounding_box={"Left": 0.1, "Top": 0.3, "Width": 0.2, "Height": 0.05})],
            ),
            TextractLine(
                text="1234567",
                confidence=60.0,
                words=[TextractWord(text="1234567", confidence=60.0, bounding_box={"Left": 0.1, "Top": 0.4, "Width": 0.2, "Height": 0.05})],
            ),
        ],
        forms=[],
        tables=[],
    )


@pytest.fixture
def mock_claude_response_general():
    """一般銀行様式のClaude応答モック"""
    response_data = {
        "form_type": "general",
        "fields": [
            {"field_name": "銀行名", "value": "みずほ銀行", "confidence_score": 88.5, "needs_review": False},
            {"field_name": "支店名", "value": "東京営業部", "confidence_score": 72.3, "needs_review": False},
            {"field_name": "口座番号", "value": "1234567", "confidence_score": 60.0, "needs_review": True},
            {"field_name": "預金者名（フリガナ）", "value": "ヤマダ タロウ", "confidence_score": 85.0, "needs_review": False},
            {"field_name": "預金者名（氏名）", "value": "山田 太郎", "confidence_score": 82.0, "needs_review": False},
        ],
        "deficiency_notes": ["委託者番号が記入されていません"],
        "correction_suggestions": {"口座番号": "1234567"},
    }

    body_content = json.dumps({
        "content": [
            {"type": "text", "text": json.dumps(response_data, ensure_ascii=False)}
        ]
    }).encode("utf-8")

    mock_response = {"body": io.BytesIO(body_content)}
    return mock_response


@pytest.fixture
def mock_claude_response_with_code_block():
    """コードブロック付きClaude応答モック"""
    response_json = {
        "form_type": "yucho",
        "fields": [
            {"field_name": "記号", "value": "10100", "confidence_score": 90.0, "needs_review": False},
            {"field_name": "番号", "value": "12345678", "confidence_score": 75.0, "needs_review": False},
        ],
        "deficiency_notes": [],
        "correction_suggestions": {},
    }

    text_with_code_block = f"以下がJSON結果です。\n```json\n{json.dumps(response_json, ensure_ascii=False)}\n```"

    body_content = json.dumps({
        "content": [
            {"type": "text", "text": text_with_code_block}
        ]
    }).encode("utf-8")

    mock_response = {"body": io.BytesIO(body_content)}
    return mock_response


class TestBuildPrompt:
    """_build_promptメソッドのテスト"""

    def test_build_prompt_includes_ocr_text(self, sample_textract_result):
        """プロンプトにOCRテキストとConfidence Scoreが含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._build_prompt(sample_textract_result)

        assert "口座振替依頼書" in prompt
        assert "みずほ銀行" in prompt
        assert "Confidence: 95.0%" in prompt
        assert "Confidence: 88.5%" in prompt

    def test_build_prompt_includes_task_instructions(self, sample_textract_result):
        """プロンプトにタスク指示が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._build_prompt(sample_textract_result)

        assert "帳票種別判定" in prompt
        assert "項目抽出" in prompt
        assert "JSON構造化" in prompt
        assert "OCR誤認識補正" in prompt
        assert "要確認判定" in prompt
        assert "不備判定" in prompt

    def test_build_prompt_includes_field_definitions(self, sample_textract_result):
        """プロンプトに抽出フィールド定義が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._build_prompt(sample_textract_result)

        assert "銀行名" in prompt
        assert "支店名" in prompt
        assert "口座番号" in prompt
        assert "預金者名（フリガナ）" in prompt
        assert "委託者番号" in prompt

    def test_build_prompt_includes_confidence_threshold(self, sample_textract_result):
        """プロンプトにConfidence閾値が含まれる"""
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._build_prompt(sample_textract_result)

        assert "70.0" in prompt

    def test_build_prompt_includes_forms_when_present(self):
        """フォーム情報がある場合、プロンプトに含まれる"""
        textract_result = TextractResult(
            lines=[TextractLine(text="テスト", confidence=90.0, words=[])],
            forms=[{"key": "銀行名", "value": "みずほ銀行", "confidence": 92.0}],
            tables=[],
        )
        client = ClaudeClient.__new__(ClaudeClient)
        prompt = client._build_prompt(textract_result)

        assert "フォーム認識結果" in prompt
        assert "銀行名: みずほ銀行" in prompt


class TestParseClaudeResponse:
    """_parse_claude_responseメソッドのテスト"""

    def test_parse_general_form_response(self, mock_claude_response_general):
        """一般銀行様式のClaude応答を正しくパースする"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        assert isinstance(result, ClaudeExtractionResult)
        assert result.form_type == FormType.GENERAL
        assert len(result.extracted_fields) == 5

    def test_parse_confidence_levels(self, mock_claude_response_general):
        """Confidence Levelが正しく判定される"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        # 銀行名: 88.5 >= 70.0 → HIGH
        bank_field = next(f for f in result.extracted_fields if f.field_name == "銀行名")
        assert bank_field.confidence_level == ConfidenceLevel.HIGH

        # 口座番号: 60.0 < 70.0 → LOW
        account_field = next(f for f in result.extracted_fields if f.field_name == "口座番号")
        assert account_field.confidence_level == ConfidenceLevel.LOW

    def test_parse_needs_review_fields(self, mock_claude_response_general):
        """要確認フィールドが正しく抽出される"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        assert "口座番号" in result.needs_review_fields

    def test_parse_deficiency_notes(self, mock_claude_response_general):
        """不備内容メモが正しく抽出される"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        assert len(result.deficiency_notes) == 1
        assert "委託者番号" in result.deficiency_notes[0]

    def test_parse_correction_suggestions(self, mock_claude_response_general):
        """補正候補が正しく抽出される"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        assert "口座番号" in result.correction_suggestions

    def test_parse_response_with_code_block(self, mock_claude_response_with_code_block):
        """コードブロック付き応答を正しくパースする"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_with_code_block)

        assert result.form_type == FormType.YUCHO
        assert len(result.extracted_fields) == 2
        assert result.extracted_fields[0].field_name == "記号"
        assert result.extracted_fields[0].value == "10100"

    def test_parse_fields_are_not_confirmed(self, mock_claude_response_general):
        """パース結果のフィールドはすべて未確認状態"""
        client = ClaudeClient.__new__(ClaudeClient)
        result = client._parse_claude_response(mock_claude_response_general)

        for field in result.extracted_fields:
            assert field.is_confirmed is False
            assert field.corrected_value is None


class TestExtractJson:
    """_extract_jsonメソッドのテスト"""

    def test_extract_json_from_code_block(self):
        """```json ... ```ブロックからJSONを抽出"""
        client = ClaudeClient.__new__(ClaudeClient)
        text = '説明文\n```json\n{"key": "value"}\n```\n追加テキスト'
        result = client._extract_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_extract_json_from_plain_block(self):
        """``` ... ```ブロックからJSONを抽出"""
        client = ClaudeClient.__new__(ClaudeClient)
        text = '```\n{"key": "value"}\n```'
        result = client._extract_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_extract_json_from_raw_text(self):
        """生のJSONテキストから抽出"""
        client = ClaudeClient.__new__(ClaudeClient)
        text = '  {"form_type": "general", "fields": []}  '
        result = client._extract_json(text)
        parsed = json.loads(result)
        assert parsed["form_type"] == "general"

    def test_extract_nested_json(self):
        """ネストされたJSONを正しく抽出"""
        client = ClaudeClient.__new__(ClaudeClient)
        text = 'Result: {"outer": {"inner": "value"}, "list": [1, 2]}'
        result = client._extract_json(text)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == "value"
        assert parsed["list"] == [1, 2]


class TestExtractFieldsWithImage:
    """extract_fields_with_imageメソッドのテスト"""

    @patch("boto3.client")
    def test_image_is_base64_encoded_in_request(self, mock_boto3_client, sample_textract_result):
        """画像がbase64エンコードされてリクエストに含まれる"""
        # モッククライアントのセットアップ
        mock_bedrock = MagicMock()
        mock_boto3_client.return_value = mock_bedrock

        response_data = {
            "content": [
                {"type": "text", "text": json.dumps({
                    "form_type": "general",
                    "fields": [],
                    "deficiency_notes": [],
                    "correction_suggestions": {},
                }, ensure_ascii=False)}
            ]
        }
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(response_data).encode("utf-8"))
        }

        client = ClaudeClient()
        client.client = mock_bedrock

        # 非同期テスト
        import asyncio
        image_bytes = b"fake_image_data"
        result = asyncio.run(client.extract_fields_with_image(sample_textract_result, image_bytes))

        # invoke_modelが呼ばれたことを確認
        mock_bedrock.invoke_model.assert_called_once()
        call_args = mock_bedrock.invoke_model.call_args
        body = json.loads(call_args[1]["body"])

        # メッセージにimage contentが含まれることを確認
        content = body["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/png"

        # base64エンコードの確認
        import base64
        expected_b64 = base64.b64encode(image_bytes).decode("utf-8")
        assert content[0]["source"]["data"] == expected_b64
