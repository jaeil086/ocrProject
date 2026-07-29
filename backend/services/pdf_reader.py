"""
PDF読み込みサービス

PyMuPDFを使用してPDFバイナリをページ単位のPNG画像に変換する。
OCR処理の前段として、高解像度（300dpi）でラスタライズを行う。
"""

import fitz  # PyMuPDF

from backend.config import PDF_RENDER_DPI


class PdfReader:
    """PDFをページ単位の高解像度画像に変換するサービス"""

    def __init__(self, dpi: int = PDF_RENDER_DPI):
        """
        初期化

        Args:
            dpi: ラスタライズ解像度。デフォルトはconfig.PDF_RENDER_DPI（300dpi）
        """
        self.dpi = dpi

    def read_pages(self, pdf_bytes: bytes) -> list[bytes]:
        """
        PDFバイナリをページごとのPNG画像バイナリに変換する。

        処理:
        1. PyMuPDFでPDFバイナリを開く
        2. 各ページを指定DPIでラスタライズ
        3. PNG形式のバイナリとして返却

        Args:
            pdf_bytes: PDFファイルのバイナリデータ

        Returns:
            list[bytes]: 各ページのPNG画像バイナリリスト

        Raises:
            ValueError: PDFデータが空の場合
            RuntimeError: PDF読み込みに失敗した場合
        """
        if not pdf_bytes:
            raise ValueError("PDFデータが空です")

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise RuntimeError(f"PDF読み込みに失敗しました: {e}") from e

        try:
            pages: list[bytes] = []
            # DPI変換: PyMuPDFのデフォルトは72dpi、指定DPIへのスケール係数を計算
            scale = self.dpi / 72
            mat = fitz.Matrix(scale, scale)

            for page in doc:
                pix = page.get_pixmap(matrix=mat)
                pages.append(pix.tobytes("png"))

            return pages
        finally:
            doc.close()
