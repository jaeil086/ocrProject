"""
監査ログモデル

OCR口座振替依頼書処理システムの監査（Audit）イベントを表現するモデル群。
ログイン・ファイル操作・OCR実行など、システム上の重要操作を記録するために使用する。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """監査イベント種別

    将来のイベント追加時はここに定義を追加する。
    値はログ集計・検索時のキーになるため、変更しないこと。
    """

    LOGIN_SUCCESS = "login_success"      # ログイン成功
    LOGIN_FAILURE = "login_failure"      # ログイン失敗
    LOGOUT = "logout"                    # ログアウト
    FILE_UPLOAD = "file_upload"          # ファイルアップロード
    OCR_EXECUTE = "ocr_execute"          # OCR実行
    RESULT_DOWNLOAD = "result_download"  # 結果ダウンロード


class AuditResult(str, Enum):
    """操作結果区分"""

    SUCCESS = "success"
    FAILURE = "failure"


class AuditLog(BaseModel):
    """監査ログ1件を表すスキーマ

    要件で指定された記録項目:
      - timestamp    : 実行日時（UTC ISO8601）
      - user_email   : 操作したユーザーのメールアドレス
      - event_type   : 実行した操作
      - target_file  : 対象ファイル名
      - ip_address   : 接続元IPアドレス
    """

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="イベント発生日時（UTC）",
    )
    event_type: AuditEventType = Field(description="監査イベント種別")
    result: AuditResult = Field(
        default=AuditResult.SUCCESS, description="操作結果（成功/失敗）"
    )
    user_email: Optional[str] = Field(
        default=None, description="操作したユーザーのメールアドレス"
    )
    user_groups: list[str] = Field(
        default_factory=list, description="ユーザーが所属するCognitoグループ"
    )
    target_file: Optional[str] = Field(
        default=None, description="操作対象のファイル名"
    )
    ip_address: Optional[str] = Field(default=None, description="接続元IPアドレス")
    user_agent: Optional[str] = Field(default=None, description="User-Agent")
    detail: Optional[str] = Field(
        default=None, description="補足情報（失敗理由・件数など）"
    )

    def to_log_line(self) -> str:
        """JSON Lines形式（1行1イベント）の文字列に変換する"""
        return self.model_dump_json()
