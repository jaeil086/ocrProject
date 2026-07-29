"""
TextractClient の単体テスト

_parse_responseメソッドのパースロジックを中心にテストする。
API呼び出し自体はAWSへの依存があるため、レスポンスパースのロジックを検証する。
"""

import pytest

from backend.services.textract_client import TextractClient


@pytest.fixture
def textract_client():
    """TextractClientインスタンス（API呼び出しはテストしない）"""
    # boto3クライアントの初期化をスキップするためにオブジェクトを直接構築
    client = object.__new__(TextractClient)
    client.client = None  # API呼び出しはモック対象
    return client


class TestParseResponse:
    """_parse_responseメソッドのテスト"""

    def test_空のレスポンスをパースできる(self, textract_client):
        """ブロックが空のレスポンスを正常にパースする"""
        response = {"Blocks": []}
        result = textract_client._parse_response(response)

        assert result.lines == []
        assert result.forms == []
        assert result.tables == []

    def test_LINEブロックをパースできる(self, textract_client):
        """LINEブロックが正しくTextractLineに変換される"""
        response = {
            "Blocks": [
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "テスト行",
                    "Confidence": 95.5,
                    "Relationships": [],
                }
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.lines) == 1
        assert result.lines[0].text == "テスト行"
        assert result.lines[0].confidence == 95.5
        assert result.lines[0].words == []

    def test_LINEブロックとWORDブロックの関連付け(self, textract_client):
        """LINEブロックに含まれるWORDブロックが正しく抽出される"""
        response = {
            "Blocks": [
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "東京 太郎",
                    "Confidence": 92.0,
                    "Relationships": [
                        {"Type": "CHILD", "Ids": ["word-1", "word-2"]}
                    ],
                },
                {
                    "Id": "word-1",
                    "BlockType": "WORD",
                    "Text": "東京",
                    "Confidence": 95.0,
                    "Geometry": {
                        "BoundingBox": {
                            "Left": 0.1,
                            "Top": 0.2,
                            "Width": 0.1,
                            "Height": 0.05,
                        }
                    },
                },
                {
                    "Id": "word-2",
                    "BlockType": "WORD",
                    "Text": "太郎",
                    "Confidence": 88.5,
                    "Geometry": {
                        "BoundingBox": {
                            "Left": 0.25,
                            "Top": 0.2,
                            "Width": 0.1,
                            "Height": 0.05,
                        }
                    },
                },
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.lines) == 1
        line = result.lines[0]
        assert line.text == "東京 太郎"
        assert len(line.words) == 2
        assert line.words[0].text == "東京"
        assert line.words[0].confidence == 95.0
        assert line.words[0].bounding_box["Left"] == 0.1
        assert line.words[1].text == "太郎"
        assert line.words[1].confidence == 88.5

    def test_KEY_VALUE_SETブロックがformsに格納される(self, textract_client):
        """KEY_VALUE_SETブロックがformsリストに格納される"""
        response = {
            "Blocks": [
                {
                    "Id": "kv-1",
                    "BlockType": "KEY_VALUE_SET",
                    "EntityTypes": ["KEY"],
                    "Confidence": 90.0,
                    "Relationships": [
                        {"Type": "VALUE", "Ids": ["kv-value-1"]}
                    ],
                }
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.forms) == 1
        assert result.forms[0]["BlockType"] == "KEY_VALUE_SET"
        assert result.lines == []
        assert result.tables == []

    def test_TABLEブロックがtablesに格納される(self, textract_client):
        """TABLEブロックがtablesリストに格納される"""
        response = {
            "Blocks": [
                {
                    "Id": "table-1",
                    "BlockType": "TABLE",
                    "Confidence": 85.0,
                    "Relationships": [
                        {"Type": "CHILD", "Ids": ["cell-1", "cell-2"]}
                    ],
                }
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.tables) == 1
        assert result.tables[0]["BlockType"] == "TABLE"
        assert result.lines == []
        assert result.forms == []

    def test_混在するブロックタイプの分類(self, textract_client):
        """LINE、KEY_VALUE_SET、TABLEが混在するレスポンスを正しく分類する"""
        response = {
            "Blocks": [
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "行1",
                    "Confidence": 90.0,
                },
                {
                    "Id": "line-2",
                    "BlockType": "LINE",
                    "Text": "行2",
                    "Confidence": 85.0,
                },
                {
                    "Id": "kv-1",
                    "BlockType": "KEY_VALUE_SET",
                    "EntityTypes": ["KEY"],
                    "Confidence": 92.0,
                },
                {
                    "Id": "table-1",
                    "BlockType": "TABLE",
                    "Confidence": 88.0,
                },
                {
                    "Id": "word-1",
                    "BlockType": "WORD",
                    "Text": "テスト",
                    "Confidence": 95.0,
                    "Geometry": {
                        "BoundingBox": {
                            "Left": 0.0,
                            "Top": 0.0,
                            "Width": 0.1,
                            "Height": 0.05,
                        }
                    },
                },
                {
                    "Id": "page-1",
                    "BlockType": "PAGE",
                    "Confidence": 100.0,
                },
            ]
        }
        result = textract_client._parse_response(response)

        # LINEブロックは2件
        assert len(result.lines) == 2
        # KEY_VALUE_SETは1件
        assert len(result.forms) == 1
        # TABLEは1件
        assert len(result.tables) == 1
        # WORDとPAGEは直接格納されない

    def test_Relationshipsがないブロック(self, textract_client):
        """Relationshipsフィールドが無いLINEブロックでもエラーにならない"""
        response = {
            "Blocks": [
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "関連なし",
                    "Confidence": 80.0,
                    # Relationships フィールド無し
                }
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.lines) == 1
        assert result.lines[0].text == "関連なし"
        assert result.lines[0].words == []

    def test_Blocksキーがないレスポンス(self, textract_client):
        """Blocksキーが無い場合は空の結果を返す"""
        response = {}
        result = textract_client._parse_response(response)

        assert result.lines == []
        assert result.forms == []
        assert result.tables == []

    def test_WORDブロックにGeometryがない場合のデフォルト値(
        self, textract_client
    ):
        """WORDブロックにGeometryがない場合はデフォルトのBoundingBoxを設定"""
        response = {
            "Blocks": [
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "テスト",
                    "Confidence": 90.0,
                    "Relationships": [
                        {"Type": "CHILD", "Ids": ["word-1"]}
                    ],
                },
                {
                    "Id": "word-1",
                    "BlockType": "WORD",
                    "Text": "テスト",
                    "Confidence": 90.0,
                    # Geometryフィールド無し
                },
            ]
        }
        result = textract_client._parse_response(response)

        assert len(result.lines[0].words) == 1
        word = result.lines[0].words[0]
        assert word.bounding_box == {
            "Left": 0.0,
            "Top": 0.0,
            "Width": 0.0,
            "Height": 0.0,
        }
