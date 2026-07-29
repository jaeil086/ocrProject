"""
ImagePreprocessor: 画像前処理サービス

Claude Sonnet 4.5は高解像度カラー画像から直接OCRを行う能力が高いため、
画像加工（二値化・ノイズ除去・傾き補正等）は行わない。
PDF→PNGで変換された画像をそのまま渡すのが最も認識精度が高い。
"""


class ImagePreprocessor:
    """画像前処理サービス — Claude直接OCRのためパススルー"""

    def preprocess(self, image_bytes: bytes) -> bytes:
        """
        画像前処理（パススルー）

        Claude Sonnet 4.5はカラー画像のほうが認識精度が高いため、
        一切の加工を行わず元画像をそのまま返却する。

        Args:
            image_bytes: 入力画像のバイナリデータ（PNG）

        Returns:
            bytes: 元画像のPNGバイナリ（加工なし）
        """
        return image_bytes
