"""
監査ログサービス

監査イベントを記録するための抽象インターフェースと、その実装を提供する。

設計方針:
  - AuditLoggerBase を抽象基底とし、出力先（JSONファイル/S3/CloudWatch/DynamoDB等）を
    差し替え可能にする。呼び出し側は record() だけを使うため、保存先が変わっても影響を受けない。
  - 初期実装は JsonFileAuditLogger（JSON Lines形式のファイル出力）。
    既存の app-logs ボリューム配下に出力する想定。
  - FastAPIのRequestから user_email / ip_address / target_file を組み立てる
    ヘルパー log_event() を提供する。

将来の拡張例:
  - S3AuditLogger  : 監査ログをS3にバッチ/逐次アップロード
  - DynamoAuditLogger : 検索性を重視しDynamoDBへ保存
  いずれも AuditLoggerBase を継承し record() を実装すればよい。
"""

import json
import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from fastapi import Request

from backend import config
from backend.models.audit import AuditEventType, AuditLog, AuditResult

logger = logging.getLogger(__name__)


class AuditLoggerBase(ABC):
    """監査ログ出力の抽象基底クラス"""

    @abstractmethod
    def record(self, entry: AuditLog) -> None:
        """監査ログ1件を永続化する"""
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        event_type: Optional[str] = None,
        user_email: Optional[str] = None,
        keyword: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """監査ログを検索して返す。

        Returns:
            (該当ログのリスト[新しい順], フィルタ後の総件数)
        戻り値のログは dict（JSONパース済み）で、新しい順（降順）に並ぶ。
        """
        raise NotImplementedError


class JsonFileAuditLogger(AuditLoggerBase):
    """JSON Lines形式でファイルに監査ログを出力する実装

    - 1イベント1行のJSONとして追記する。
    - 日付ごとにファイルを分割する（audit-YYYYMMDD.log）。
    - スレッドセーフに追記する（バックグラウンドタスクからの同時書き込みに対応）。
    """

    def __init__(self, log_dir: Path):
        self._log_dir = log_dir
        self._lock = threading.Lock()
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # ディレクトリ作成失敗時も起動は継続する
            logger.error(f"監査ログディレクトリ作成失敗: {e}")

    def _current_file(self, entry: AuditLog) -> Path:
        date_str = entry.timestamp.strftime("%Y%m%d")
        return self._log_dir / f"audit-{date_str}.log"

    def record(self, entry: AuditLog) -> None:
        line = entry.to_log_line()
        target = self._current_file(entry)
        try:
            with self._lock:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            # 監査ログの書き込み失敗が業務処理を止めないよう、ログ出力のみに留める
            logger.error(f"監査ログ書き込み失敗: {e} / entry={line}")

    def _target_files(
        self, date_from: Optional[str], date_to: Optional[str]
    ) -> list[Path]:
        """日付範囲に該当するログファイルを新しい順に返す。

        ファイル名は audit-YYYYMMDD.log。date_from / date_to は "YYYY-MM-DD" 想定。
        """
        try:
            files = sorted(self._log_dir.glob("audit-*.log"))
        except Exception as e:
            logger.error(f"監査ログディレクトリの読み取り失敗: {e}")
            return []

        def _file_date(p: Path) -> str:
            # "audit-20260909.log" -> "2026-09-09"
            stem = p.stem  # audit-20260909
            digits = stem.replace("audit-", "")
            if len(digits) == 8:
                return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
            return ""

        selected: list[Path] = []
        for p in files:
            d = _file_date(p)
            if not d:
                continue
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            selected.append(p)

        # 新しい日付のファイルを先に処理する（降順）
        return list(reversed(selected))

    def query(
        self,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        event_type: Optional[str] = None,
        user_email: Optional[str] = None,
        keyword: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """JSON Linesのログファイルを読み、フィルタ・ソート・ページングして返す。"""
        files = self._target_files(date_from, date_to)

        matched: list[dict] = []
        kw = keyword.lower() if keyword else None
        email_f = user_email.lower() if user_email else None

        with self._lock:
            for path in files:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception as e:
                    logger.error(f"監査ログ読み取り失敗: {path}: {e}")
                    continue

                # ファイル内も新しい行が下にあるため、逆順で読む（新しい順）
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        # 壊れた行はスキップ
                        continue

                    if event_type and rec.get("event_type") != event_type:
                        continue
                    if email_f:
                        rec_email = (rec.get("user_email") or "").lower()
                        if email_f not in rec_email:
                            continue
                    if kw and kw not in line.lower():
                        continue

                    matched.append(rec)

        total = len(matched)
        page = matched[offset : offset + limit]
        return page, total


def _build_logger() -> AuditLoggerBase:
    """設定に応じた監査ロガー実装を生成する"""
    backend = config.AUDIT_LOG_BACKEND.lower()
    if backend == "json":
        return JsonFileAuditLogger(config.AUDIT_LOG_DIR)
    # 未対応のバックエンド指定時はJSONにフォールバック
    logger.warning(
        f"未対応の AUDIT_LOG_BACKEND='{backend}' が指定されました。JSONファイル出力にフォールバックします。"
    )
    return JsonFileAuditLogger(config.AUDIT_LOG_DIR)


# シングルトンインスタンス
audit_logger: AuditLoggerBase = _build_logger()


def _client_ip(request: Optional[Request]) -> Optional[str]:
    """リクエストから接続元IPを取得する

    Nginxが付与する X-Forwarded-For を優先し、先頭（最も外側のクライアント）を採用する。
    """
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


def log_event(
    event_type: AuditEventType,
    *,
    request: Optional[Request] = None,
    user_email: Optional[str] = None,
    user_groups: Optional[list[str]] = None,
    target_file: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: Optional[str] = None,
) -> None:
    """監査イベントを記録する共通ヘルパー

    FastAPIのRequestからIP・User-Agentを補完しつつ、AuditLogを組み立てて永続化する。
    ルーターやサービスからはこの関数を呼び出すだけでよい。
    """
    entry = AuditLog(
        event_type=event_type,
        result=result,
        user_email=user_email,
        user_groups=user_groups or [],
        target_file=target_file,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        detail=detail,
    )
    audit_logger.record(entry)


def log_event_ctx(
    event_type: AuditEventType,
    ctx: dict,
    *,
    target_file: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: Optional[str] = None,
) -> None:
    """バックグラウンドタスク用の監査イベント記録ヘルパー

    Requestを持てないバックグラウンド処理向けに、あらかじめ収集した
    コンテキスト（user_email / user_groups / ip_address / user_agent）から記録する。
    """
    entry = AuditLog(
        event_type=event_type,
        result=result,
        user_email=ctx.get("user_email"),
        user_groups=ctx.get("user_groups") or [],
        target_file=target_file,
        ip_address=ctx.get("ip_address"),
        user_agent=ctx.get("user_agent"),
        detail=detail,
    )
    audit_logger.record(entry)
