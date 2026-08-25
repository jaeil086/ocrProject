"""
アプリケーション設定

OCR口座振替依頼書処理システムの設定値を定義する。
環境変数が設定されている場合はそちらを優先し、未設定時はデフォルト値を使用する。
"""

import os
from pathlib import Path

# === プロジェクトパス ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"

# === OCR Confidence Score 閾値 ===
CONFIDENCE_THRESHOLD: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "70.0"))

# === AWS設定 ===
AWS_REGION: str = os.environ.get("AWS_REGION", "ap-northeast-1")  # Tokyo
AWS_BEDROCK_SERVICE: str = "bedrock-runtime"

# 東京リージョンInference Profile（SCPで東京・大阪・バージニア以外制限のため 「jp.」 プレフィックスを使用）
BEDROCK_INFERENCE_PROFILE_ID: str = os.environ.get(
    "BEDROCK_INFERENCE_PROFILE_ID", "jp.anthropic.claude-sonnet-4-6"
)

# === ファイルサイズ上限 ===
MAX_FILE_SIZE_BYTES: int = int(os.environ.get("MAX_FILE_SIZE_BYTES", str(50 * 1024 * 1024)))

# === PDF処理設定 ===
# 300dpiで十分なOCR精度を確保しつつ、画像サイズを大幅に削減（600dpi比で1/4）
PDF_RENDER_DPI: int = int(os.environ.get("PDF_RENDER_DPI", "300"))

# === リトライ設定 ===
BEDROCK_MAX_RETRIES: int = int(os.environ.get("BEDROCK_MAX_RETRIES", "3"))
BEDROCK_RETRY_MIN_WAIT: int = int(os.environ.get("BEDROCK_RETRY_MIN_WAIT", "2"))
BEDROCK_RETRY_MAX_WAIT: int = int(os.environ.get("BEDROCK_RETRY_MAX_WAIT", "15"))

# === Claude プロンプト設定 ===
CLAUDE_MAX_TOKENS: int = int(os.environ.get("CLAUDE_MAX_TOKENS", "1024"))


# === 金融機関マスター設定 ===
# Zengin Code API URL
ZENGIN_BANKS_URL: str = "https://zengin-code.github.io/api/banks.json"
ZENGIN_BRANCHES_URL_TEMPLATE: str = "https://zengin-code.github.io/api/branches/{bank_code}.json"

# マスターデータキャッシュパス
ZENGIN_CACHE_DIR = DATA_DIR / "zengin_cache"
ZENGIN_BANKS_CACHE_FILE = ZENGIN_CACHE_DIR / "banks.json"
ZENGIN_BRANCHES_CACHE_DIR = ZENGIN_CACHE_DIR / "branches"

# キャッシュ有効期限（秒）: 24時間
ZENGIN_CACHE_TTL_SECONDS: int = 86400

# Fuzzy Matching 閾値
MASTER_MATCH_OK_THRESHOLD: float = 95.0       # 95%以上 → OK（自動確定）
MASTER_MATCH_REVIEW_THRESHOLD: float = 85.0   # 85%以上 → 確認必要
# 85%未満 → NG

# === S3設定 ===
S3_BUCKET_NAME: str = os.environ.get("S3_BUCKET_NAME", "cheiru-ocr-storage")
S3_INPUT_PREFIX: str = os.environ.get("S3_INPUT_PREFIX", "00_input")
S3_OUTPUT_PREFIX: str = os.environ.get("S3_OUTPUT_PREFIX", "01_output")
S3_ARCHIVE_PREFIX: str = os.environ.get("S3_ARCHIVE_PREFIX", "02_archive")
