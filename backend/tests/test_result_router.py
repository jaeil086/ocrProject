"""
結果操作API群の統合テスト

GET /api/result/{file_id}: 処理結果取得
PUT /api/result/{file_id}/fields: フィールド修正
PUT /api/result/{file_id}/visual-checks: 目視確認更新
POST /api/result/{file_id}/confirm: 確認完了
GET /api/result/{file_id}/csv: CSVダウンロード
GET /api/result/{file_id}/pdf: PDFダウンロード
"""

import pytest


# === GET /api/result/{file_id} ===


@pytest.mark.asyncio
async def test_get_result_success(client, sample_document):
    """正常系: 存在するfile_idで結果を取得できる"""
    response = await client.get("/api/result/test-001")

    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == "test-001"
    assert data["original_filename"] == "test.pdf"
    assert data["form_type"] == "general"
    assert data["status"] == "needs_review"
    assert len(data["fields"]) == 5
    assert len(data["visual_checks"]) == 4


@pytest.mark.asyncio
async def test_get_result_not_found(client):
    """異常系: 存在しないfile_idは404を返す"""
    response = await client.get("/api/result/nonexistent")

    assert response.status_code == 404
    data = response.json()
    assert "見つかりません" in data["detail"]


# === PUT /api/result/{file_id}/fields ===


@pytest.mark.asyncio
async def test_update_field_success(client, sample_document):
    """正常系: フィールドの修正値を設定できる"""
    response = await client.put(
        "/api/result/test-001/fields",
        json={
            "field_name": "支店名",
            "corrected_value": "東京中央支店",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["field_name"] == "支店名"
    assert data["corrected_value"] == "東京中央支店"
    assert data["is_confirmed"] is True
    # 元のvalueが保持されていることを確認
    assert data["value"] == "東京営業部"


@pytest.mark.asyncio
async def test_update_field_document_not_found(client):
    """異常系: 存在しないfile_idでのフィールド修正は404を返す"""
    response = await client.put(
        "/api/result/nonexistent/fields",
        json={
            "field_name": "銀行名",
            "corrected_value": "テスト銀行",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_field_not_found(client, sample_document):
    """異常系: 存在しないフィールド名での修正は404を返す"""
    response = await client.put(
        "/api/result/test-001/fields",
        json={
            "field_name": "存在しないフィールド",
            "corrected_value": "テスト",
        },
    )

    assert response.status_code == 404
    data = response.json()
    assert "見つかりません" in data["detail"]


# === PUT /api/result/{file_id}/visual-checks ===


@pytest.mark.asyncio
async def test_update_visual_check_success(client, sample_document):
    """正常系: 目視確認ステータスを更新できる"""
    response = await client.put(
        "/api/result/test-001/visual-checks",
        json={
            "check_item": "金融機関お届け印",
            "is_checked": True,
            "checked_by": "テスト担当者",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["check_item"] == "金融機関お届け印"
    assert data["is_checked"] is True
    assert data["checked_by"] == "テスト担当者"
    assert data["checked_at"] is not None


@pytest.mark.asyncio
async def test_update_visual_check_uncheck(client, sample_document):
    """正常系: 目視確認をチェック解除できる"""
    # まずチェックする
    await client.put(
        "/api/result/test-001/visual-checks",
        json={
            "check_item": "金融機関お届け印",
            "is_checked": True,
            "checked_by": "テスト担当者",
        },
    )

    # チェック解除
    response = await client.put(
        "/api/result/test-001/visual-checks",
        json={
            "check_item": "金融機関お届け印",
            "is_checked": False,
            "checked_by": "テスト担当者",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_checked"] is False
    assert data["checked_at"] is None


@pytest.mark.asyncio
async def test_update_visual_check_not_found(client, sample_document):
    """異常系: 存在しない確認項目名での更新は404を返す"""
    response = await client.put(
        "/api/result/test-001/visual-checks",
        json={
            "check_item": "存在しない項目",
            "is_checked": True,
            "checked_by": "テスト担当者",
        },
    )

    assert response.status_code == 404
    data = response.json()
    assert "見つかりません" in data["detail"]


# === POST /api/result/{file_id}/confirm ===


@pytest.mark.asyncio
async def test_confirm_document_success(client, sample_document):
    """正常系: 確認完了処理でconfirmed_atとconfirmed_byが設定される"""
    response = await client.post(
        "/api/result/test-001/confirm",
        json={"confirmed_by": "確認担当者A"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["confirmed_by"] == "確認担当者A"
    assert data["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_confirm_document_not_found(client):
    """異常系: 存在しないfile_idでの確認完了は404を返す"""
    response = await client.post(
        "/api/result/nonexistent/confirm",
        json={"confirmed_by": "テスト"},
    )

    assert response.status_code == 404


# === GET /api/result/{file_id}/csv ===


@pytest.mark.asyncio
async def test_download_csv_success(client, sample_document):
    """正常系: CSVファイルがShift_JISで返却される"""
    response = await client.get("/api/result/test-001/csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "content-disposition" in response.headers

    # Content-Dispositionにファイル名が含まれることを確認
    content_disposition = response.headers["content-disposition"]
    assert "attachment" in content_disposition

    # Shift_JISでデコードできることを確認
    csv_content = response.content.decode("shift_jis")
    assert "FileID" in csv_content
    assert "test-001" in csv_content


@pytest.mark.asyncio
async def test_download_csv_not_found(client):
    """異常系: 存在しないfile_idでのCSVダウンロードは404を返す"""
    response = await client.get("/api/result/nonexistent/csv")

    assert response.status_code == 404


# === GET /api/result/{file_id}/pdf ===


@pytest.mark.asyncio
async def test_download_pdf_success(client, sample_document):
    """正常系: リネーム済みPDFが返却される"""
    response = await client.get("/api/result/test-001/pdf")

    assert response.status_code == 200
    assert "application/pdf" in response.headers["content-type"]
    assert "content-disposition" in response.headers

    # Content-Dispositionにファイル名が含まれることを確認
    content_disposition = response.headers["content-disposition"]
    assert "attachment" in content_disposition

    # PDFバイナリが返却されることを確認
    assert response.content == b"fake pdf bytes for testing"


@pytest.mark.asyncio
async def test_download_pdf_not_found(client):
    """異常系: 存在しないfile_idでのPDFダウンロードは404を返す"""
    response = await client.get("/api/result/nonexistent/pdf")

    assert response.status_code == 404
