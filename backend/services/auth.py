"""
認証・認可サービス（AWS Cognito JWT検証）

Cognitoが発行するJWT（IDトークン / アクセストークン）を検証し、
認証済みユーザー情報をFastAPIの依存関数として提供する。

設計方針:
  - Cognito Hosted UI + Authorization Code Flow で取得したトークンを httpOnly Cookie に保持し、
    APIリクエスト時に Cookie（または Authorization ヘッダー）から取り出して検証する。
  - JWKS（公開鍵）はCognitoのエンドポイントから取得し、メモリにキャッシュする。
  - iss / aud（またはclient_id）/ exp / 署名 を検証する。
  - Cognito Group（"cognito:groups"）からロールを抽出し、認可に利用する。

将来のEntra ID等SSO連携について:
  - Cognitoを外部IdP（SAML/OIDC）のフェデレーションハブとして使うため、
    アプリが検証するのは常に「Cognitoが発行したJWT」となる。
    そのため、IdPがEntra IDに変わっても本モジュールの検証ロジックは変更不要。
"""

import logging
import time
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel

from backend import config

logger = logging.getLogger(__name__)

# Cookie名
ACCESS_TOKEN_COOKIE = "ocr_access_token"
ID_TOKEN_COOKIE = "ocr_id_token"
REFRESH_TOKEN_COOKIE = "ocr_refresh_token"


class AuthenticatedUser(BaseModel):
    """認証済みユーザー情報"""

    sub: str                     # Cognitoのユーザー一意ID
    email: Optional[str] = None  # メールアドレス
    groups: list[str] = []       # 所属Cognitoグループ（ロール）
    username: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return config.COGNITO_GROUP_ADMIN in self.groups


class _JwksCache:
    """CognitoのJWKSをメモリにキャッシュする

    公開鍵のローテーションに追随するため、一定時間（TTL）でキャッシュを更新する。
    未知のkidが来た場合も強制的に再取得する。
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = ttl_seconds
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0

    def _fetch(self) -> None:
        if not config.COGNITO_JWKS_URL:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cognitoが設定されていません（COGNITO_USER_POOL_ID / COGNITO_REGION を確認してください）",
            )
        try:
            resp = httpx.get(config.COGNITO_JWKS_URL, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"JWKS取得失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="認証基盤（JWKS）への接続に失敗しました",
            )
        self._keys = {k["kid"]: k for k in data.get("keys", [])}
        self._fetched_at = time.time()

    def get_key(self, kid: str) -> Optional[dict]:
        expired = (time.time() - self._fetched_at) > self._ttl
        if not self._keys or expired or kid not in self._keys:
            self._fetch()
        return self._keys.get(kid)


_jwks_cache = _JwksCache()


def verify_token(token: str) -> AuthenticatedUser:
    """JWTを検証し、認証済みユーザー情報を返す

    署名・iss・exp を検証する。aud はIDトークン/アクセストークンで扱いが異なるため、
    Cognitoの慣例に合わせて検証する:
      - IDトークン    : aud == client_id
      - アクセストークン: client_id クレーム == client_id（audは無い）
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"トークンの形式が不正です: {e}",
        )

    kid = header.get("kid")
    key = _jwks_cache.get_key(kid) if kid else None
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンの署名鍵が見つかりません",
        )

    try:
        # 署名・iss・expを検証する。
        # - verify_aud: audience はトークン種別により扱いが異なるため後段で手動判定する。
        # - verify_at_hash: IDトークンには at_hash（access_tokenのハッシュ）が含まれるが、
        #   access_token を渡さずに検証しようとすると失敗する。BFF方式ではサーバーが
        #   トークンを直接受領しており、署名/iss/aud/exp検証で十分なため at_hash 検証は無効化する。
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=config.COGNITO_ISSUER,
            options={"verify_aud": False, "verify_at_hash": False},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"トークン検証に失敗しました: {e}",
        )

    # audience / client_id 検証
    token_use = claims.get("token_use")
    if token_use == "id":
        if claims.get("aud") != config.COGNITO_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="トークンの発行先(aud)が一致しません",
            )
    elif token_use == "access":
        if claims.get("client_id") != config.COGNITO_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="トークンのクライアントIDが一致しません",
            )

    return AuthenticatedUser(
        sub=claims.get("sub", ""),
        email=claims.get("email"),
        groups=claims.get("cognito:groups", []) or [],
        username=claims.get("cognito:username") or claims.get("username"),
    )


def _extract_token(request: Request) -> Optional[str]:
    """リクエストからトークンを取り出す

    優先順位:
      1. httpOnly Cookie（BFF方式の通常経路）
      2. Authorization: Bearer ヘッダー（API直接呼び出し・デバッグ用）
    IDトークンにemail等のプロフィールが載るため、IDトークンを優先的に使用する。
    """
    id_token = request.cookies.get(ID_TOKEN_COOKIE)
    if id_token:
        return id_token
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if access_token:
        return access_token
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


async def get_current_user(request: Request) -> AuthenticatedUser:
    """認証済みユーザーを返すFastAPI依存関数

    AUTH_ENABLED=false の場合は開発用のダミーユーザーを返し、認証をバイパスする。
    トークンが無い/不正な場合は 401 を返す。
    """
    if not config.AUTH_ENABLED:
        return AuthenticatedUser(
            sub="dev-local",
            email="dev@example.com",
            groups=[config.COGNITO_GROUP_ADMIN],
            username="dev",
        )

    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(token)


def require_groups(*allowed_groups: str):
    """指定グループのいずれかに属することを要求する依存関数を生成する

    使用例:
        @router.post(..., dependencies=[Depends(require_groups(config.COGNITO_GROUP_ADMIN))])
    """

    async def _checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not config.AUTH_ENABLED:
            return user
        if allowed_groups and not any(g in user.groups for g in allowed_groups):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="この操作を行う権限がありません",
            )
        return user

    return _checker
