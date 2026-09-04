"""
FastAPIアプリケーションエントリポイント

OCR口座振替依頼書処理システムのメインアプリケーション。
CORS設定、ルーター登録、例外ハンドラーを定義する。

起動コマンド: uvicorn backend.main:app --reload
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# === カスタム例外クラス ===


class OcrProcessingError(Exception):
    """OCR処理エラー"""

    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(self.message)


# === FastAPIアプリケーション作成 ===

app = FastAPI(
    title="OCR口座振替依頼書処理システム",
    description="口座振替依頼書PDFをOCR処理し、データ検証・CSV出力・PDFリネームを行うAPI",
    version="1.0.0",
)


# === CORS設定 ===
# BFF方式ではブラウザ→Nginx→(同一オリジンの)/api というプロキシ経由になるため、
# 本番では ALLOWED_ORIGINS を明示し、Cookie送信を許可する。
# allow_credentials=True の場合、ワイルドカード "*" は使用できない点に注意。
import os as _os

_allowed_origins_env = _os.environ.get("ALLOWED_ORIGINS", "")
if _allowed_origins_env:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
else:
    # 開発時のデフォルト（Next.js dev）
    _allowed_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === 例外ハンドラー ===


@app.exception_handler(OcrProcessingError)
async def ocr_processing_error_handler(
    request: Request, exc: OcrProcessingError
) -> JSONResponse:
    """OCR処理エラーのハンドラー"""
    return JSONResponse(
        status_code=500,
        content={"error": exc.message, "detail": exc.detail},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """入力値エラーのハンドラー"""
    return JSONResponse(
        status_code=400,
        content={"error": "入力値が不正です", "detail": str(exc)},
    )


# === ルーター登録 ===

try:
    from backend.routers.auth import router as auth_router
    app.include_router(auth_router)
    logger.info("auth router 登録成功")
except Exception as e:
    logger.error(f"auth router 登録失敗: {e}", exc_info=True)

try:
    from backend.routers.upload import router as upload_router
    app.include_router(upload_router)
    logger.info("upload router 登録成功")
except Exception as e:
    logger.error(f"upload router 登録失敗: {e}", exc_info=True)

try:
    from backend.routers.result import router as result_router
    app.include_router(result_router)
    logger.info("result router 登録成功")
except Exception as e:
    logger.error(f"result router 登録失敗: {e}", exc_info=True)

try:
    from backend.routers.batch import router as batch_router
    app.include_router(batch_router)
    logger.info("batch router 登録成功")
except Exception as e:
    logger.error(f"batch router 登録失敗: {e}", exc_info=True)


# === 起動時イベント: 金融機関マスター初期化 ===


@app.on_event("startup")
async def startup_load_zengin_master():
    """FastAPI起動時に金融機関マスターデータをロード"""
    from backend.services.zengin_master import ZenginMasterService

    try:
        await ZenginMasterService.initialize()
        logger.info("金融機関マスター初期化完了")
    except Exception as e:
        logger.error(f"金融機関マスター初期化失敗（OCR処理は継続可能）: {e}", exc_info=True)


# === ヘルスチェックエンドポイント ===


@app.get("/", tags=["health"])
async def health_check() -> dict:
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok", "service": "OCR口座振替依頼書処理システム"}
