"""
認証ルーター（AWS Cognito / Authorization Code Flow / BFF方式）

エンドポイント:
  GET  /api/auth/login    : Cognito Hosted UIのログイン画面へリダイレクト
  GET  /api/auth/callback : Cognitoからのコールバック。認可コードをトークンに交換し、
                            httpOnly Cookieに保存してアプリのトップへ戻す
  POST /api/auth/logout   : Cookieを破棄し、Cognitoのログアウトへリダイレクト
  GET  /api/auth/me       : ログイン中ユーザー情報（メール・グループ）を返す

トークンはすべて httpOnly / Secure Cookie に保存し、ブラウザのJavaScriptからは
参照できないようにする（XSS対策）。
"""

import base64
import hashlib
import logging
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from backend import config
from backend.models.audit import AuditEventType, AuditResult
from backend.services import auth as auth_service
from backend.services.audit_logger import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# CSRF対策のstate、PKCE用のCookie名
_STATE_COOKIE = "ocr_oauth_state"
_PKCE_COOKIE = "ocr_pkce_verifier"

# Cookieの最大有効期間（秒）。リフレッシュトークン運用に合わせて調整可能。
_COOKIE_MAX_AGE = 60 * 60  # 1時間（アクセス/IDトークンの有効期限に合わせる）
_REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30日


def _cookie_secure() -> bool:
    """本番（HTTPS）ではSecure属性を付与する。認証無効時のローカルはFalse。"""
    return config.AUTH_ENABLED


def _set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    id_token: str,
    refresh_token: str | None,
) -> None:
    """認証Cookieを設定する

    認証・認可（get_current_user）に必要なのはIDトークンのみのため、
    IDトークン1本だけをCookieに保存する。
    アクセストークン・リフレッシュトークンは現状の認可判定では未使用であり、
    3本すべてを保存するとSet-Cookieヘッダーが肥大化してプロキシ(nginx)の
    ヘッダーバッファ上限を超える（502 upstream sent too big header）ため保存しない。

    リフレッシュトークンによる自動再発行を将来実装する際は、必要に応じて
    別パス（例: /api/auth 配下）に限定してリフレッシュトークンCookieを付与し、
    全リクエストでは送信されないよう path を絞ること。
    """
    secure = _cookie_secure()
    common = dict(httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(
        auth_service.ID_TOKEN_COOKIE, id_token, max_age=_COOKIE_MAX_AGE, **common
    )


def _clear_auth_cookies(response: Response) -> None:
    """認証関連Cookieを削除する"""
    for name in (
        auth_service.ACCESS_TOKEN_COOKIE,
        auth_service.ID_TOKEN_COOKIE,
        auth_service.REFRESH_TOKEN_COOKIE,
        _STATE_COOKIE,
        _PKCE_COOKIE,
    ):
        response.delete_cookie(name, path="/")


def _pkce_pair() -> tuple[str, str]:
    """PKCE の code_verifier と code_challenge(S256) を生成する"""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


@router.get("/login")
async def login() -> RedirectResponse:
    """Cognito Hosted UIのログイン画面へリダイレクトする"""
    if not config.COGNITO_DOMAIN or not config.COGNITO_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cognitoが設定されていません（COGNITO_DOMAIN / COGNITO_CLIENT_ID）",
        )

    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()

    params = {
        "client_id": config.COGNITO_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": config.COGNITO_REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{config.COGNITO_DOMAIN}/oauth2/authorize?{urllib.parse.urlencode(params)}"

    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    # state / verifier を短命Cookieに保存（コールバックで検証）
    secure = _cookie_secure()
    response.set_cookie(
        _STATE_COOKIE, state, max_age=600, httponly=True, secure=secure, samesite="lax", path="/"
    )
    response.set_cookie(
        _PKCE_COOKIE, verifier, max_age=600, httponly=True, secure=secure, samesite="lax", path="/"
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None):
    """Cognitoからのリダイレクトを受け取り、認可コードをトークンに交換する"""
    error = request.query_params.get("error")
    if error:
        log_event(
            AuditEventType.LOGIN_FAILURE,
            request=request,
            result=AuditResult.FAILURE,
            detail=f"cognito_error={error}",
        )
        return RedirectResponse(url="/?login_error=1", status_code=status.HTTP_302_FOUND)

    if not code:
        raise HTTPException(status_code=400, detail="認可コードがありません")

    # CSRF: state検証
    saved_state = request.cookies.get(_STATE_COOKIE)
    if not saved_state or saved_state != state:
        log_event(
            AuditEventType.LOGIN_FAILURE,
            request=request,
            result=AuditResult.FAILURE,
            detail="state_mismatch",
        )
        raise HTTPException(status_code=400, detail="stateが一致しません（不正なリクエスト）")

    verifier = request.cookies.get(_PKCE_COOKIE)

    # トークンエンドポイントへ交換リクエスト
    token_url = f"{config.COGNITO_DOMAIN}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": config.COGNITO_CLIENT_ID,
        "code": code,
        "redirect_uri": config.COGNITO_REDIRECT_URI,
    }
    if verifier:
        data["code_verifier"] = verifier

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    # Client Secretを使う場合はBasic認証を付与
    if config.COGNITO_CLIENT_SECRET:
        basic = base64.b64encode(
            f"{config.COGNITO_CLIENT_ID}:{config.COGNITO_CLIENT_SECRET}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {basic}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(token_url, data=data, headers=headers)
    except Exception as e:
        logger.error(f"トークン交換リクエスト失敗: {e}")
        log_event(
            AuditEventType.LOGIN_FAILURE,
            request=request,
            result=AuditResult.FAILURE,
            detail="token_endpoint_unreachable",
        )
        raise HTTPException(status_code=502, detail="認証基盤への接続に失敗しました")

    if token_resp.status_code != 200:
        logger.error(f"トークン交換失敗: {token_resp.status_code} {token_resp.text}")
        log_event(
            AuditEventType.LOGIN_FAILURE,
            request=request,
            result=AuditResult.FAILURE,
            detail=f"token_exchange_status={token_resp.status_code}",
        )
        raise HTTPException(status_code=401, detail="トークン交換に失敗しました")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    id_token = tokens.get("id_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token or not id_token:
        raise HTTPException(status_code=401, detail="トークンが取得できませんでした")

    # 取得したIDトークンを検証し、ユーザー情報を確定（成功ログにemailを残すため）
    try:
        user = auth_service.verify_token(id_token)
    except HTTPException:
        log_event(
            AuditEventType.LOGIN_FAILURE,
            request=request,
            result=AuditResult.FAILURE,
            detail="id_token_verify_failed",
        )
        raise

    # ログイン成功をリダイレクトレスポンスとして返し、Cookieを設定
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(
        response,
        access_token=access_token,
        id_token=id_token,
        refresh_token=refresh_token,
    )
    # 使い終わったstate/verifier Cookieを削除
    response.delete_cookie(_STATE_COOKIE, path="/")
    response.delete_cookie(_PKCE_COOKIE, path="/")

    log_event(
        AuditEventType.LOGIN_SUCCESS,
        request=request,
        user_email=user.email,
        user_groups=user.groups,
        result=AuditResult.SUCCESS,
    )
    logger.info(f"ログイン成功: {user.email}")
    return response


@router.post("/logout")
async def logout(request: Request):
    """ログアウトしCookieを破棄する。Cognitoのログアウトエンドポイントへ誘導する。"""
    # ログアウト対象のユーザーを可能な範囲で特定（監査用）
    email = None
    token = request.cookies.get(auth_service.ID_TOKEN_COOKIE)
    if token:
        try:
            email = auth_service.verify_token(token).email
        except Exception:
            email = None

    logout_url = "/"
    if config.COGNITO_DOMAIN and config.COGNITO_CLIENT_ID:
        params = {
            "client_id": config.COGNITO_CLIENT_ID,
            "logout_uri": config.COGNITO_LOGOUT_REDIRECT_URI,
        }
        logout_url = f"{config.COGNITO_DOMAIN}/logout?{urllib.parse.urlencode(params)}"

    response = JSONResponse(content={"logout_url": logout_url})
    _clear_auth_cookies(response)

    log_event(
        AuditEventType.LOGOUT,
        request=request,
        user_email=email,
        result=AuditResult.SUCCESS,
    )
    return response


@router.get("/me")
async def me(request: Request):
    """ログイン中のユーザー情報を返す（未認証時は401）"""
    user = await auth_service.get_current_user(request)
    return {
        "email": user.email,
        "username": user.username,
        "groups": user.groups,
        "is_admin": user.is_admin,
    }
