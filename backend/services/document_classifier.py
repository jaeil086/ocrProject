"""
書類仕分けロジック

ValidationError有無とConfidenceLevel判定に基づき、
書類を3分類（NORMAL/DEFICIENT/NEEDS_REVIEW）に仕分ける。
"""

from backend.models.enums import ConfidenceLevel, DocumentStatus
from backend.models.schemas import OcrField, ValidationError


class DocumentClassifier:
    """書類仕分けロジック"""

    def classify(
        self,
        fields: list[OcrField],
        validation_errors: list[ValidationError],
    ) -> DocumentStatus:
        """
        ValidationError有無とConfidenceLevel判定に基づく3分類

        判定順序:
        1. バリデーションエラーがある → DEFICIENT
        2. 確認未完了の低Confidenceフィールドがある → NEEDS_REVIEW
        3. 上記いずれでもない → NORMAL
        """
        # 不備あり: バリデーションエラーがある場合
        if validation_errors:
            return DocumentStatus.DEFICIENT

        # 要確認: Confidence Scoreが閾値未満で未確認のフィールドがある場合
        for field in fields:
            if field.confidence_level == ConfidenceLevel.LOW and not field.is_confirmed:
                return DocumentStatus.NEEDS_REVIEW

        # 正常: すべてのチェックが正常
        return DocumentStatus.NORMAL
