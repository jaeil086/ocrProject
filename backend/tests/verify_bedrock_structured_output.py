"""
Bedrock InvokeModel + output_config (Structured Outputs) 実機検証スクリプト

目的:
  - output_configがリクエストbodyに含まれてAWSに送信されるか確認
  - ValidationException / Unknown parameter エラーが発生しないか確認
  - 応答が純粋なJSONのみで返ってくるか確認

使用方法:
  .venv\Scripts\python.exe backend\tests\verify_bedrock_structured_output.py
"""

import json
import sys
import time

import boto3

# テスト用の簡易スキーマ（実際のSTEP2_OUTPUT_SCHEMAの縮小版）
TEST_SCHEMA = {
    "type": "object",
    "properties": {
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
        "口座番号": {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"]},
                "confidence": {"type": "integer"}
            },
            "required": ["value", "confidence"],
            "additionalProperties": False
        }
    },
    "required": ["銀行名", "支店名", "口座番号"],
    "additionalProperties": False
}

# 設定
MODEL_ID = "jp.anthropic.claude-sonnet-4-6"
REGION = "ap-northeast-1"


def main():
    print("=" * 70)
    print("Bedrock InvokeModel + output_config 実機検証")
    print("=" * 70)
    print(f"\nモデルID: {MODEL_ID}")
    print(f"リージョン: {REGION}")
    print(f"スキーマ: {json.dumps(TEST_SCHEMA, ensure_ascii=False, indent=2)}")
    print()

    # リクエストボディ構築
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "以下のテキストから金融機関情報を抽出してください。\n\n"
                            "テキスト: みずほ銀行 東京営業部 口座番号 1234567"
                        ),
                    }
                ],
            }
        ],
        # ★ 検証対象: output_config
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": TEST_SCHEMA,
            }
        },
    }

    print("-" * 70)
    print("[1] 送信リクエストbody（output_config含む）:")
    print("-" * 70)
    print(json.dumps(request_body, ensure_ascii=False, indent=2))
    print()

    # Bedrock呼び出し
    print("-" * 70)
    print("[2] Bedrock InvokeModel 呼び出し実行...")
    print("-" * 70)

    client = boto3.client("bedrock-runtime", region_name=REGION)

    start_time = time.time()
    try:
        response = client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body),
        )
        elapsed = time.time() - start_time
        print(f"✓ 呼び出し成功（{elapsed:.2f}秒）")
        print(f"  HTTPステータス: {response['ResponseMetadata']['HTTPStatusCode']}")
        print()
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ エラー発生（{elapsed:.2f}秒）")
        print(f"  エラータイプ: {type(e).__name__}")
        print(f"  エラーメッセージ: {e}")
        sys.exit(1)

    # レスポンス解析
    print("-" * 70)
    print("[3] レスポンス原文（response_body）:")
    print("-" * 70)
    response_body = json.loads(response["body"].read())
    print(json.dumps(response_body, ensure_ascii=False, indent=2))
    print()

    # JSON検証
    print("-" * 70)
    print("[4] JSON純粋性検証:")
    print("-" * 70)
    content = response_body.get("content", [])
    text_response = ""
    for block in content:
        if block.get("type") == "text":
            text_response = block.get("text", "")
            break

    print(f"  応答テキスト: {text_response}")
    print()

    try:
        parsed = json.loads(text_response)
        print("✓ json.loads() 成功 — 純粋なJSONとして直接パース可能")
        print(f"  パース結果: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
    except json.JSONDecodeError as e:
        print(f"✗ json.loads() 失敗 — JSON以外のテキストが混在")
        print(f"  エラー: {e}")
        sys.exit(1)

    # スキーマ準拠チェック
    print()
    print("-" * 70)
    print("[5] スキーマ準拠チェック:")
    print("-" * 70)
    required_fields = TEST_SCHEMA["required"]
    all_present = True
    for field in required_fields:
        if field in parsed:
            field_data = parsed[field]
            if isinstance(field_data, dict) and "value" in field_data and "confidence" in field_data:
                print(f"  ✓ {field}: value={field_data['value']}, confidence={field_data['confidence']}")
            else:
                print(f"  ✗ {field}: 構造が不正 → {field_data}")
                all_present = False
        else:
            print(f"  ✗ {field}: 欠落")
            all_present = False

    # 余分なフィールドチェック
    extra_fields = set(parsed.keys()) - set(required_fields)
    if extra_fields:
        print(f"  ⚠ 余分なフィールド: {extra_fields}")
        all_present = False

    print()
    print("=" * 70)
    if all_present and not extra_fields:
        print("★ 検証結果: すべてパス — output_config (Structured Outputs) 正常動作確認")
    else:
        print("★ 検証結果: 一部問題あり")
    print("=" * 70)


if __name__ == "__main__":
    main()
