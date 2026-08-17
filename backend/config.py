"""
アプリケーション設定

OCR口座振替依頼書処理システムの設定値を定義する。
"""

from pathlib import Path

# === プロジェクトパス ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"

# === OCR Confidence Score 閾値 ===
CONFIDENCE_THRESHOLD: float = 70.0

# === AWS設定 ===
AWS_REGION: str = "ap-northeast-1"  #Tokyo
AWS_BEDROCK_SERVICE: str = "bedrock-runtime"

# 東京リージョンInference Profile（SCPで東京・大阪・バージニア以外制限のため 「jp.」 プレフィックスを使用）
# BEDROCK_INFERENCE_PROFILE_ID: str = "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"
BEDROCK_INFERENCE_PROFILE_ID: str = "jp.anthropic.claude-sonnet-4-6"

# === ファイルサイズ上限 ===
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024

# === PDF処理設定 ===
# 300dpiで十分なOCR精度を確保しつつ、画像サイズを大幅に削減（600dpi比で1/4）
PDF_RENDER_DPI: int = 300

# === リトライ設定 ===
BEDROCK_MAX_RETRIES: int = 3
BEDROCK_RETRY_MIN_WAIT: int = 2
BEDROCK_RETRY_MAX_WAIT: int = 15

# === Claude プロンプト設定  / 'max_tokens': 1024  === 
# CLAUDE_MAX_TOKENS: int = 8192  
CLAUDE_MAX_TOKENS: int = 1024  


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

# === S3 PREFIX :클라우드 원격처리.  ===
S3_BUCKET_NAME = "cheiru-ocr-storage"
S3_INPUT_PREFIX = "00_input"
S3_OUTPUT_PREFIX = "01_output"
S3_ARCHIVE_PREFIX = "02_archive"
 