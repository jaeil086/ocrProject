"""
監査ログ閲覧ルーター（管理者限定）

エンドポイント:
  GET /api/audit/logs        : 監査ログを検索して返す（管理者のみ）
  GET /api/audit/event-types : 選択可能なイベント種別の一覧を返す

権限:
  Cognitoグループが管理者（config.COGNITO_GROUP_ADMIN）のユーザーのみアクセス可能。
  require_groups により、それ以外は 403 を返す。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend import config
from backend.models.audit import AuditEventType
from backend.services.audit_logger import audit_logger
from backend.services.auth import AuthenticatedUser, require_groups

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
async def get_audit_logs(
    date_from: Optional[str] = Query(
        None, description="開始日 (YYYY-MM-DD)。この日を含む"
    ),
    date_to: Optional[str] = Query(
        None, description="終了日 (YYYY-MM-DD)。この日を含む"
    ),
    event_type: Optional[str] = Query(
        None, description="イベント種別でフィルタ（例: login_success）"
    ),
    user_email: Optional[str] = Query(
        None, description="ユーザーメールで部分一致フィルタ"
    ),
    keyword: Optional[str] = Query(None, description="行全体へのキーワード部分一致"),
    offset: int = Query(0, ge=0, description="取得開始位置（ページング用）"),
    limit: int = Query(100, ge=1, le=1000, description="取得件数（最大1000）"),
    _user: AuthenticatedUser = Depends(
        require_groups(config.COGNITO_GROUP_ADMIN)
    ),
):
    """監査ログを新しい順に検索して返す（管理者限定）。"""
    logs, total = audit_logger.query(
        date_from=date_from,
        date_to=date_to,
        event_type=event_type,
        user_email=user_email,
        keyword=keyword,
        offset=offset,
        limit=limit,
    )
    return {
        "logs": logs,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/event-types")
async def get_event_types(
    _user: AuthenticatedUser = Depends(
        require_groups(config.COGNITO_GROUP_ADMIN)
    ),
):
    """フィルタで選択できるイベント種別の一覧を返す（管理者限定）。"""
    return {
        "event_types": [
            {"value": e.value, "label": e.value} for e in AuditEventType
        ]
    }
