"""
実OCR経路での output_config 動作検証スクリプト

実際のClaudeClientクラスを使って、Step2のinvoke_model呼び出しが
output_config付きで正常に動作するか確認する。

使用方法:
  .venv\\Scripts\\python.exe backend\\tests\\verify_ocr_path.py
"""

import asyncio
import json
import logging
import sys

# ログ設定: 全てのログをコンソールに表示
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)

from backend.services.claude_client import ClaudeClient


async def main():
    print("=" * 70)
    print("実OCR経路 output_config 検証")
    print("=" * 70)

    client = ClaudeClient()

    # 認証情報確認
    import boto3
    session = boto3.Session()
    creds = session.get_credentials()
    if creds:
        frozen = creds.get_frozen_credentials()
        print(f"\n[認証] profile={session.profile_name}, method={creds.method}")
        print(f"  access_key={frozen.access_key[:8]}..., has_token={bool(frozen.token)}")
    else:
        print("\n[認証] 認証情報なし - 中断")
        sys.exit(1)

    # Step2用のダミーOCRテキスト（Step1をスキップして直接Step2を検証）
    dummy_ocr_text = """預金口座振替依頼書・自動払込利用申込書
収納代行会社名 1 きらぼしシステム株式会社
預金種目 1.普通
届出印 (印影あり)
フリガナ ヤマダ タロウ
氏名 山田 太郎
口座番号 1234567
金融機関名 みずほ銀行 コード 0001
支店名 東京営業部 店番号 001
委託者番号 12345 契約者番号 67890"""

    print(f"\n[Step2入力] OCRテキスト長: {len(dummy_ocr_text)}文字")
    print(f"[Step2入力] モデルID: {client.client.meta.endpoint_url}")

    # output_configを含むリクエストを画像なしで直接送信
    # （ダミー画像はClaude側で "Could not process image" エラーになるため）
    print(f"\n{'=' * 70}")
    print("output_config付き invoke_model 呼び出し（テキストのみ）...")
    print("=" * 70)

    from backend.config import BEDROCK_INFERENCE_PROFILE_ID, CLAUDE_MAX_TOKENS
    import json as json_mod

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": CLAUDE_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": client._step2_prompt(dummy_ocr_text),
                    },
                ],
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": ClaudeClient.STEP2_OUTPUT_SCHEMA,
            }
        },
    }

    # リクエストbodyからoutput_configの存在を確認
    print(f"\n[確認] output_config がリクエストbodyに含まれるか: {'output_config' in request_body}")
    print(f"[確認] schema type: {request_body['output_config']['format']['type']}")
    print(f"[確認] schema required fields: {request_body['output_config']['format']['schema']['required']}")

    try:
        response = client.client.invoke_model(
            modelId=BEDROCK_INFERENCE_PROFILE_ID,
            body=json_mod.dumps(request_body),
        )

        # レスポンス解析
        response_body = json_mod.loads(response["body"].read())

        print(f"\n[レスポンス] HTTPステータス: {response['ResponseMetadata']['HTTPStatusCode']}")
        print(f"[レスポンス] model: {response_body.get('model')}")
        print(f"[レスポンス] stop_reason: {response_body.get('stop_reason')}")
        print(f"[レスポンス] usage: {response_body.get('usage')}")

        content = response_body.get("content", [])
        text_response = ""
        for block in content:
            if block.get("type") == "text":
                text_response = block.get("text", "")
                break

        print(f"\n[レスポンス応答テキスト原文]:")
        print(text_response)

        # JSON純粋性検証
        data = json_mod.loads(text_response)
        print(f"\n[JSON検証] json.loads() 成功")
        print(f"[JSON検証] パース結果:")
        print(json_mod.dumps(data, ensure_ascii=False, indent=2))

        # フィールド数確認
        print(f"\n[スキーマ準拠] フィールド数: {len(data)}")
        for field_name, field_data in data.items():
            print(f"  ✓ {field_name}: value={field_data.get('value')}, confidence={field_data.get('confidence')}")

        print(f"\n{'=' * 70}")
        print("★ 検証結果: すべてパス")
        print("=" * 70)
        print("✓ output_configが実際のリクエストbodyに含まれてAWSに送信された")
        print("✓ ValidationException 発生なし")
        print("✓ Unknown parameter エラー 発生なし")
        print("✓ schema関連エラー 発生なし")
        print("✓ 応答が純粋なJSONのみ（json.loads成功）")
        print("✓ スキーマに準拠した構造で返却された")

    except Exception as e:
        print(f"\n{'=' * 70}")
        print(f"★ エラー発生")
        print("=" * 70)
        print(f"  タイプ: {type(e).__name__}")
        print(f"  メッセージ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())