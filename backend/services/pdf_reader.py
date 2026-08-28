"""
PDF読み込みサービス

PyMuPDFを使用してPDFバイナリをページ単位のPNG画像に変換する。
OCR処理の前段として、高解像度（300dpi）でラスタライズを行う。
複数ページPDFを個別の1ページPDFに分割する機能も提供する。
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

    def get_page_count(self, pdf_bytes: bytes) -> int:
        """
        PDFのページ数を取得する。

        Args:
            pdf_bytes: PDFファイルのバイナリデータ

        Returns:
            int: ページ数

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
            return len(doc)
        finally:
            doc.close()

    def split_pages(self, pdf_bytes: bytes) -> list[bytes]:
        """
        複数ページPDFを1ページずつの個別PDFバイナリに分割する。

        複合機でスキャンした際に1つのPDFにまとめられた複数の
        預金口座振替届出書を、ページ単位で個別のPDFファイルとして分割する。

        Args:
            pdf_bytes: PDFファイルのバイナリデータ（複数ページ可）

        Returns:
            list[bytes]: 各ページの個別PDFバイナリリスト。
                         1ページのPDFの場合はそのまま1要素のリストを返す。

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
            page_count = len(doc)

            # 1ページの場合はそのまま返す（再エンコード不要）
            if page_count == 1:
                return [pdf_bytes]

            # 複数ページの場合、各ページを個別PDFとして書き出す
            split_pdfs: list[bytes] = []
            for page_num in range(page_count):
                # 新しい空のPDFドキュメントを作成
                new_doc = fitz.open()
                # 元PDFから該当ページをコピー
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                # PDFバイナリとして書き出し
                split_pdfs.append(new_doc.tobytes())
                new_doc.close()

            return split_pdfs
        finally:
            doc.close()
