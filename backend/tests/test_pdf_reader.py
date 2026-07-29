"""
PdfReaderサービスのユニットテスト

PyMuPDFによるPDF→PNG画像変換の動作を検証する。
"""

import fitz  # PyMuPDF
import pytest

from backend.services.pdf_reader import PdfReader


def _create_test_pdf(num_pages: int = 1) -> bytes:
    """テスト用の最小PDFバイナリを生成する"""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4サイズ
        # テスト用にテキストを追加
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPdfReader:
    """PdfReaderのユニットテスト"""

    def test_read_single_page_pdf(self):
        """1ページPDFから1つのPNG画像が返ることを検証"""
        pdf_bytes = _create_test_pdf(num_pages=1)
        reader = PdfReader()

        result = reader.read_pages(pdf_bytes)

        assert len(result) == 1
        # PNG形式のヘッダ（マジックバイト）を検証
        assert result[0][:8] == b"\x89PNG\r\n\x1a\n"

    def test_read_multi_page_pdf(self):
        """複数ページPDFからページ数分のPNG画像が返ることを検証"""
        pdf_bytes = _create_test_pdf(num_pages=3)
        reader = PdfReader()

        result = reader.read_pages(pdf_bytes)

        assert len(result) == 3
        for page_png in result:
            assert page_png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_read_pages_returns_bytes(self):
        """各ページがbytes型で返されることを検証"""
        pdf_bytes = _create_test_pdf(num_pages=2)
        reader = PdfReader()

        result = reader.read_pages(pdf_bytes)

        for page_png in result:
            assert isinstance(page_png, bytes)
            assert len(page_png) > 0

    def test_custom_dpi(self):
        """カスタムDPI指定時にも正常に動作することを検証"""
        pdf_bytes = _create_test_pdf(num_pages=1)
        reader_150 = PdfReader(dpi=150)
        reader_300 = PdfReader(dpi=300)

        result_150 = reader_150.read_pages(pdf_bytes)
        result_300 = reader_300.read_pages(pdf_bytes)

        # 300dpiの方が150dpiより大きい画像になるはず
        assert len(result_300[0]) > len(result_150[0])

    def test_empty_pdf_bytes_raises_value_error(self):
        """空バイトデータで ValueError が発生することを検証"""
        reader = PdfReader()

        with pytest.raises(ValueError, match="PDFデータが空です"):
            reader.read_pages(b"")

    def test_invalid_pdf_bytes_raises_runtime_error(self):
        """不正なバイナリデータで RuntimeError が発生することを検証"""
        reader = PdfReader()

        with pytest.raises(RuntimeError, match="PDF読み込みに失敗しました"):
            reader.read_pages(b"this is not a pdf")

    def test_default_dpi_from_config(self):
        """デフォルトDPIがconfig.PDF_RENDER_DPIから取得されることを検証"""
        from backend.config import PDF_RENDER_DPI

        reader = PdfReader()

        assert reader.dpi == PDF_RENDER_DPI
