"""
モデルパッケージ

列挙型およびPydanticモデルを公開する。
"""

from backend.models.enums import (
    ConfidenceLevel,
    DocumentStatus,
    FormType,
    ValidationErrorType,
    VisualCheckType,
)
from backend.models.schemas import (
    ClaudeExtractionResult,
    ConfirmRequest,
    FieldUpdateRequest,
    FinancialInstitution,
    OcrDocument,
    OcrField,
    ProcessingResult,
    TextractLine,
    TextractResult,
    TextractWord,
    UploadResponse,
    ValidationError,
    VisualCheck,
    VisualCheckUpdateRequest,
)

__all__ = [
    # 列挙型
    "FormType",
    "DocumentStatus",
    "ConfidenceLevel",
    "ValidationErrorType",
    "VisualCheckType",
    # コアモデル
    "OcrField",
    "ValidationError",
    "VisualCheck",
    "OcrDocument",
    "ProcessingResult",
    "FinancialInstitution",
    # Textract結果モデル
    "TextractWord",
    "TextractLine",
    "TextractResult",
    # Claude抽出結果モデル
    "ClaudeExtractionResult",
    # リクエスト/レスポンスモデル
    "UploadResponse",
    "FieldUpdateRequest",
    "VisualCheckUpdateRequest",
    "ConfirmRequest",
]
