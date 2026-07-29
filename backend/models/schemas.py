"""
Pydanticモデル定義

OCR口座振替依頼書処理システムで使用するデータモデルを定義する。
コアモデル、Textract結果モデル、Claude抽出結果モデル、
およびリクエスト/レスポンスモデルを含む。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import (
    ConfidenceLevel,
    DocumentStatus,
    FormType,
    ValidationErrorType,
    VisualCheckType,
)


# === コアモデル ===


class OcrField(BaseModel):
    """OCR認識フィールド"""

    field_name: str  # フィールド名
    value: Optional[str] = None  # 認識値
    confidence_score: float = Field(ge=0, le=100)  # Confidence Score (0-100)
    confidence_level: ConfidenceLevel  # 判定レベル
    is_confirmed: bool = False  # 担当者確認済みフラグ
    corrected_value: Optional[str] = None  # 修正値


class ValidationError(BaseModel):
    """バリデーションエラー"""

    field_name: str  # 対象フィールド名
    error_type: ValidationErrorType  # エラー種別
    message: str  # エラーメッセージ


class VisualCheck(BaseModel):
    """目視確認項目"""

    check_item: str  # 確認項目名
    check_type: VisualCheckType  # 確認種別
    is_checked: bool = False  # 確認完了フラグ
    checked_by: Optional[str] = None  # 確認者
    checked_at: Optional[datetime] = None  # 確認日時


class OcrDocument(BaseModel):
    """OCR処理ドキュメント（メインモデル）"""

    file_id: str  # FileID
    original_filename: str  # アップロード時ファイル名
    form_type: Optional[FormType] = None  # 帳票様式区分
    status: DocumentStatus  # 処理ステータス
    fields: list[OcrField] = []  # OCR認識フィールドリスト
    validation_errors: list[ValidationError] = []  # バリデーションエラーリスト
    visual_checks: list[VisualCheck] = []  # 目視確認項目リスト
    # ファイル名生成に必要な項目（fieldsから抽出）
    consignor_number: Optional[str] = None  # 委託者番号
    contract_number: Optional[str] = None  # 契約番号
    bank_name: Optional[str] = None  # 銀行名
    branch_name: Optional[str] = None  # 支店名
    bank_code: Optional[str] = None  # 銀行番号
    branch_code: Optional[str] = None  # 店番号
    account_number: Optional[str] = None  # 口座番号
    depositor_name: Optional[str] = None  # 預金者名
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    confirmed_at: Optional[datetime] = None  # 確認完了日時
    confirmed_by: Optional[str] = None  # 確認者名
    # PDF原本バイナリ（インメモリ保持・レスポンスには含めない）
    pdf_bytes: Optional[bytes] = Field(default=None, exclude=True)


class ProcessingResult(BaseModel):
    """OCRパイプライン処理結果"""

    document: OcrDocument
    success: bool
    error_message: Optional[str] = None


class FinancialInstitution(BaseModel):
    """金融機関マスタ"""

    bank_code: str = Field(min_length=4, max_length=4)  # 金融機関コード（4桁）
    bank_name: str  # 金融機関名
    branch_code: str = Field(min_length=3, max_length=3)  # 店番号（3桁）
    branch_name: str  # 支店名


# === Textract結果モデル ===


class TextractWord(BaseModel):
    """Textract認識単語"""

    text: str
    confidence: float
    bounding_box: dict  # {Left, Top, Width, Height}


class TextractLine(BaseModel):
    """Textract認識行"""

    text: str
    confidence: float
    words: list[TextractWord]


class TextractResult(BaseModel):
    """Textract OCR結果"""

    lines: list[TextractLine]
    forms: list[dict]  # Key-Valueペア
    tables: list[dict]  # テーブル構造


# === Claude抽出結果モデル ===


class ClaudeExtractionResult(BaseModel):
    """Claude文書理解結果"""

    form_type: FormType
    extracted_fields: list[OcrField]
    needs_review_fields: list[str]  # 要確認フィールド名リスト
    deficiency_notes: list[str]  # 不備内容メモ
    correction_suggestions: dict[str, str]  # {フィールド名: 補正候補}


# === リクエスト/レスポンスモデル ===


class UploadResponse(BaseModel):
    """アップロード + OCR処理レスポンス"""

    files: list[dict]  # [{file_id, original_filename, status, fields, errors}]
    total_count: int


class FieldUpdateRequest(BaseModel):
    """フィールド修正リクエスト"""

    field_name: str
    corrected_value: str


class VisualCheckUpdateRequest(BaseModel):
    """目視確認更新リクエスト"""

    check_item: str
    is_checked: bool
    checked_by: str


class ConfirmRequest(BaseModel):
    """確認完了リクエスト"""

    confirmed_by: str
