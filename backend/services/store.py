"""
InMemoryStore: 処理結果のインメモリ保持（セッション単位）

データ永続保存は行わず、処理結果はdictで保持する。
セッション終了後にデータは破棄される。
"""

from typing import Optional

from backend.models.schemas import OcrDocument


class InMemoryStore:
    """処理結果のインメモリ保持（セッション単位）"""

    def __init__(self) -> None:
        self._documents: dict[str, OcrDocument] = {}
        self._pdf_bytes: dict[str, bytes] = {}

    def save(self, document: OcrDocument, pdf_bytes: bytes) -> None:
        """OcrDocumentとPDFバイナリを保存する"""
        self._documents[document.file_id] = document
        self._pdf_bytes[document.file_id] = pdf_bytes

    def get(self, file_id: str) -> Optional[OcrDocument]:
        """file_idに対応するOcrDocumentを取得する（存在しない場合はNone）"""
        return self._documents.get(file_id)

    def get_pdf(self, file_id: str) -> Optional[bytes]:
        """file_idに対応するPDFバイナリを取得する（存在しない場合はNone）"""
        return self._pdf_bytes.get(file_id)

    def update(self, document: OcrDocument) -> None:
        """OcrDocumentを更新する（PDFバイナリはそのまま保持）"""
        self._documents[document.file_id] = document

    def delete(self, file_id: str) -> None:
        """file_idに対応するOcrDocumentとPDFバイナリを削除する"""
        self._documents.pop(file_id, None)
        self._pdf_bytes.pop(file_id, None)


# グローバルストア（アプリケーションライフサイクルに紐づくシングルトン）
store = InMemoryStore()
