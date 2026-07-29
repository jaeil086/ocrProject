"""
テストフィクスチャ

バックエンド統合テスト用の共通フィクスチャを定義する。
- InMemoryStoreの初期化・リセット
- テスト用HTTPクライアント（httpx AsyncClient）
- サンプルドキュメント生成
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.enums import (
    ConfidenceLevel,
    DocumentStatus,
    FormType,
    VisualCheckType,
)
from backend.models.schemas import OcrDocument, OcrField, VisualCheck
from backend.services.store import store


@pytest.fixture(autouse=True)
def clean_store():
    """各テスト前にストアをリセット"""
    store._documents.clear()
    store._pdf_bytes.clear()
    yield
    store._documents.clear()
    store._pdf_bytes.clear()


@pytest.fixture
async def client():
    """テスト用HTTPクライアント"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_document():
    """テスト用のOcrDocumentを作成してストアに保存"""
    doc = OcrDocument(
        file_id="test-001",
        original_filename="test.pdf",
        form_type=FormType.GENERAL,
        status=DocumentStatus.NEEDS_REVIEW,
        fields=[
            OcrField(
                field_name="預金者名（フリガナ）",
                value="タナカ タロウ",
                confidence_score=95.0,
                confidence_level=ConfidenceLevel.HIGH,
                is_confirmed=False,
            ),
            OcrField(
                field_name="預金者名（氏名）",
                value="田中 太郎",
                confidence_score=90.0,
                confidence_level=ConfidenceLevel.HIGH,
                is_confirmed=False,
            ),
            OcrField(
                field_name="銀行名",
                value="みずほ銀行",
                confidence_score=85.0,
                confidence_level=ConfidenceLevel.HIGH,
                is_confirmed=False,
            ),
            OcrField(
                field_name="支店名",
                value="東京営業部",
                confidence_score=60.0,
                confidence_level=ConfidenceLevel.LOW,
                is_confirmed=False,
            ),
            OcrField(
                field_name="口座番号",
                value="1234567",
                confidence_score=75.0,
                confidence_level=ConfidenceLevel.HIGH,
                is_confirmed=False,
            ),
        ],
        validation_errors=[],
        visual_checks=[
            VisualCheck(
                check_item="金融機関お届け印",
                check_type=VisualCheckType.SEAL,
            ),
            VisualCheck(
                check_item="銀行・信用金庫・組合の選択",
                check_type=VisualCheckType.CIRCLE_MARK,
            ),
            VisualCheck(
                check_item="預金種目の選択",
                check_type=VisualCheckType.CIRCLE_MARK,
            ),
            VisualCheck(
                check_item="収納代行会社",
                check_type=VisualCheckType.AGENCY_CHECK,
            ),
        ],
        consignor_number="12345",
        contract_number="67890",
    )
    store.save(doc, b"fake pdf bytes for testing")
    return doc
