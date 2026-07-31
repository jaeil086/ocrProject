"""
ImagePreprocessor: 画像前処理サービス

Bedrock API上限（5MB）に収まるようJPEG圧縮する。
600dpi PNGは高解像度だがサイズが大きいため、必要に応じて圧縮する。
"""

import cv2
import numpy as np

# Bedrock画像サイズ上限（余裕を持たせて4.5MB）
MAX_IMAGE_BYTES = 4_500_000


class ImagePreprocessor:
    """画像前処理サービス — サイズ圧縮のみ"""

    def preprocess(self, image_bytes: bytes) -> bytes:
        """
        画像前処理: サイズがBedrock上限を超える場合にJPEG圧縮する。
        上限以内ならそのまま返す。

        Args:
            image_bytes: 入力画像のバイナリデータ（PNG）

        Returns:
            bytes: 処理済み画像バイナリ（PNG or JPEG）
        """
        if len(image_bytes) <= MAX_IMAGE_BYTES:
            return image_bytes

        try:
            # PNG→numpy配列にデコード
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return image_bytes

            # JPEG品質を段階的に下げて4.5MB以内に収める
            for quality in [95, 90, 85, 80, 70, 60]:
                _, buffer = cv2.imencode(
                    ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                jpg_bytes = buffer.tobytes()
                if len(jpg_bytes) <= MAX_IMAGE_BYTES:
                    return jpg_bytes

            # それでも超える場合はリサイズ
            h, w = img.shape[:2]
            scale = 0.7
            resized = cv2.resize(img, (int(w * scale), int(h * scale)))
            _, buffer = cv2.imencode(
                ".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            return buffer.tobytes()

        except Exception:
            return image_bytes
