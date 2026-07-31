"""
AWS認証環境の確認スクリプト

verify_bedrock_structured_output.pyの実行環境と
FastAPI(uvicorn)実行環境の差異を特定する。
"""

import os
import sys

import boto3


def main():
    print("=" * 70)
    print("AWS認証環境チェック")
    print("=" * 70)

    # 1. 環境変数 AWS_PROFILE
    print("\n[1] AWS_PROFILE 環境変数:")
    aws_profile = os.environ.get("AWS_PROFILE", "(未設定)")
    print(f"  AWS_PROFILE = {aws_profile}")

    # 関連する環境変数も確認
    print("\n  関連環境変数:")
    for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "AWS_DEFAULT_REGION", "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"]:
        val = os.environ.get(key)
        if val:
            # シークレットは先頭4文字のみ表示
            if "SECRET" in key or "TOKEN" in key or "KEY" in key:
                print(f"  {key} = {val[:4]}****（設定あり）")
            else:
                print(f"  {key} = {val}")
        else:
            print(f"  {key} = (未設定)")

    # 2. boto3.Session().get_credentials()
    print("\n[2] boto3.Session().get_credentials():")
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials:
        creds = credentials.get_frozen_credentials()
        print(f"  access_key = {creds.access_key[:4]}****" if creds.access_key else "  access_key = None")
        print(f"  secret_key = {'設定あり' if creds.secret_key else 'None'}")
        print(f"  token = {'設定あり' if creds.token else 'None（長期認証）'}")
        print(f"  method = {credentials.method}")
    else:
        print("  認証情報なし (None)")

    # 3. boto3.Session().profile_name
    print("\n[3] boto3.Session().profile_name:")
    print(f"  profile_name = {session.profile_name}")

    # 4. BEDROCK_INFERENCE_PROFILE_ID
    print("\n[4] BEDROCK_INFERENCE_PROFILE_ID:")
    try:
        from backend.config import BEDROCK_INFERENCE_PROFILE_ID, AWS_REGION
        print(f"  BEDROCK_INFERENCE_PROFILE_ID = {BEDROCK_INFERENCE_PROFILE_ID}")
        print(f"  AWS_REGION = {AWS_REGION}")
    except ImportError as e:
        print(f"  インポートエラー: {e}")

    # 5. AWSプロファイル一覧
    print("\n[5] ~/.aws/credentials と ~/.aws/config の存在確認:")
    home = os.path.expanduser("~")
    cred_path = os.path.join(home, ".aws", "credentials")
    config_path = os.path.join(home, ".aws", "config")
    print(f"  {cred_path}: {'存在' if os.path.exists(cred_path) else '不在'}")
    print(f"  {config_path}: {'存在' if os.path.exists(config_path) else '不在'}")

    # プロファイル一覧
    if os.path.exists(config_path):
        print("\n  config内のプロファイル:")
        try:
            with open(config_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("["):
                        print(f"    {line}")
        except Exception as e:
            print(f"    読取エラー: {e}")

    # 6. 実際にbedrock-runtimeクライアント作成を試行
    print("\n[6] bedrock-runtime クライアント作成テスト:")
    try:
        client = boto3.client("bedrock-runtime", region_name="ap-northeast-1")
        # list_foundation_models等は不要、クライアント作成自体が成功するか
        print(f"  ✓ クライアント作成成功")
        print(f"  endpoint: {client.meta.endpoint_url}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")

    print("\n" + "=" * 70)
    print("※ FastAPI(uvicorn)側で認証が通る場合、")
    print("   uvicorn起動時に別のAWS_PROFILEや環境変数が設定されている可能性があります。")
    print("   .vscode/launch.json や起動スクリプトの環境変数を確認してください。")
    print("=" * 70)


if __name__ == "__main__":
    main()
