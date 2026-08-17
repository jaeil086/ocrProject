"""
ImagePreprocessor: 画像前処理サービス

Bedrock API上限（5MB）に収まるようJPEG圧縮する。
300dpi PNGは通常3～5MB程度のため、ほとんどのケースでパススルーとなる。
上限を超える場合のみJPEG圧縮を実行する。
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Bedrock画像サイズ上限（余裕を持たせて4.5MB）
MAX_IMAGE_BYTES = 4_500_000


class ImagePreprocessor:
    """画像前処理サービス — サイズ圧縮のみ（300dpiではほぼパススルー）"""

    def preprocess(self, image_bytes: bytes) -> bytes:
        """
        画像前処理: サイズがBedrock上限を超える場合にJPEG圧縮する。
        上限以内ならそのまま返す（300dpiではほとんどの場合パススルー）。

        Args:
            image_bytes: 入力画像のバイナリデータ（PNG）

        Returns:
            bytes: 処理済み画像バイナリ（PNG or JPEG）
        """
        if len(image_bytes) <= MAX_IMAGE_BYTES:
            logger.debug(
                f"画像サイズ {len(image_bytes)/1024:.0f}KB — 上限以内のためパススルー"
            )
            return image_bytes

        logger.info(
            f"画像サイズ {len(image_bytes)/1024:.0f}KB — 上限超過のためJPEG圧縮実行"
        )

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
