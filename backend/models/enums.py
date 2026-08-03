"""
列挙型定義

OCR口座振替依頼書処理システムで使用する列挙型を定義する。
"""

from enum import Enum


class FormType(str, Enum):
    """帳票様式区分"""
    YUCHO = "yucho"           # ゆうちょ銀行様式
    GENERAL = "general"       # 一般銀行様式


class DocumentStatus(str, Enum):
    """書類ステータス"""
    UPLOADING = "uploading"       # アップロード中
    PROCESSING = "processing"     # 処理中
    NORMAL = "normal"             # 正常
    DEFICIENT = "deficient"       # 不備あり
    NEEDS_REVIEW = "needs_review"  # 要確認


class ConfidenceLevel(str, Enum):
    """Confidence Score判定レベル"""
    HIGH = "high"   # 閾値以上（自動確定）
    LOW = "low"     # 閾値未満（要確認）


class ValidationErrorType(str, Enum):
    """バリデーションエラー種別"""
    MISSING_FIELD = "記入漏れ"
    BANK_CODE_MISMATCH = "銀行番号不一致"
    BRANCH_CODE_MISMATCH = "店番号不一致"
    BANK_CODE_NOT_FOUND = "銀行番号不存在"
    BRANCH_CODE_NOT_FOUND = "店番号不存在"


class VisualCheckType(str, Enum):
    """目視確認種別"""
    SEAL = "目視確認必要"              # 届出印
    CIRCLE_MARK = "目視確認必要"       # 〇印選択
    AGENCY_CHECK = "確認者チェック必要"  # 収納代行会社


# === バッチ処理用列挙型 ===


class BatchFileStatus(str, Enum):
    """バッチ処理ファイルステータス"""
    QUEUED = "queued"               # 待機中
    PROCESSING = "processing"       # 処理中
    COMPLETED = "completed"         # 完了
    NEEDS_REVIEW = "needs_review"   # 確認必要
    FAILED = "failed"               # 失敗


class BatchJobStatus(str, Enum):
    """バッチジョブ全体ステータス"""
    UPLOADING = "uploading"         # アップロード中
    PROCESSING = "processing"       # 処理中
    COMPLETED = "completed"         # 全件完了
    PARTIAL = "partial"             # 一部失敗あり
