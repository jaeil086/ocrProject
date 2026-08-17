"""
ImagePreprocessorのユニットテスト

テスト画像を動的に生成し、サイズ圧縮処理の動作を検証する。
現在のImagePreprocessorはBedrock API上限（4.5MB）超過時のみJPEG圧縮を行い、
それ以外はパススルーする。
"""

import cv2
import numpy as np
import pytest

from backend.services.image_preprocessor import ImagePreprocessor, MAX_IMAGE_BYTES


@pytest.fixture
def preprocessor():
    """ImagePreprocessorインスタンスを返すフィクスチャ"""
    return ImagePreprocessor()


def _create_test_image(width: int = 300, height: int = 200, color: bool = True) -> bytes:
    """テスト用のカラー画像をPNGバイナリとして生成する（上限以内のサイズ）"""
    if color:
        img = np.ones((height, width, 3), dtype=np.uint8) * 255
        cv2.line(img, (20, 50), (280, 50), (0, 0, 0), 2)
        cv2.line(img, (20, 100), (280, 100), (0, 0, 0), 2)
        cv2.line(img, (20, 150), (280, 150), (0, 0, 0), 2)
    else:
        img = np.ones((height, width), dtype=np.uint8) * 255
        cv2.line(img, (20, 50), (280, 50), 0, 2)

    _, buffer = cv2.imencode(".png", img)
    return buffer.tobytes()


def _create_large_image(size_mb: float = 5.0) -> bytes:
    """Bedrock上限を超える大きな画像を生成する"""
    # ランダムなカラー画像を生成して大きなPNGにする
    # PNGはランダムデータだと圧縮率が低いためサイズが大きくなる
    height = 3000
    width = 4000
    img = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".png", img)
    png_bytes = buffer.tobytes()

    # サイズが上限を超えない場合、画像を大きくして再生成
    if len(png_bytes) <= MAX_IMAGE_BYTES:
        # さらに大きな画像で再試行
        height = 5000
        width = 6000
        img = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        _, buffer = cv2.imencode(".png", img)
        png_bytes = buffer.tobytes()

    return png_bytes


class TestImagePreprocessor:
    """ImagePreprocessorのテストスイート"""

    def test_preprocess_returns_bytes(self, preprocessor):
        """preprocess()がbytes型を返すことを確認"""
        image_bytes = _create_test_image()
        result = preprocessor.preprocess(image_bytes)
        assert isinstance(result, bytes)

    def test_preprocess_passthrough_under_limit(self, preprocessor):
        """上限以内の画像はそのまま返される（パススルー）"""
        image_bytes = _create_test_image()
        assert len(image_bytes) <= MAX_IMAGE_BYTES

        result = preprocessor.preprocess(image_bytes)
        # パススルーなので完全に同一
        assert result == image_bytes

    def test_preprocess_returns_valid_image(self, preprocessor):
        """preprocess()の出力がデコード可能な画像であることを確認"""
        image_bytes = _create_test_image()
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        assert decoded is not None

    def test_preprocess_preserves_dimensions_when_under_limit(self, preprocessor):
        """上限以内の画像のサイズが保持されることを確認"""
        width, height = 300, 200
        image_bytes = _create_test_image(width=width, height=height)
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        assert decoded.shape[:2] == (height, width)

    def test_preprocess_compresses_large_image(self, preprocessor):
        """上限超過の画像がJPEG圧縮されて上限以内になる"""
        large_image = _create_large_image()

        # テスト前提: 画像が上限を超えていること
        if len(large_image) <= MAX_IMAGE_BYTES:
            pytest.skip("テスト画像が上限を超えていないためスキップ")

        result = preprocessor.preprocess(large_image)
        assert len(result) <= MAX_IMAGE_BYTES

    def test_preprocess_compressed_output_is_jpeg(self, preprocessor):
        """上限超過時の出力がJPEG形式になる"""
        large_image = _create_large_image()

        if len(large_image) <= MAX_IMAGE_BYTES:
            pytest.skip("テスト画像が上限を超えていないためスキップ")

        result = preprocessor.preprocess(large_image)
        # JPEG先頭バイト: 0xFF 0xD8
        assert result[:2] == b'\xff\xd8'

    def test_preprocess_with_invalid_data_returns_original(self, preprocessor):
        """無効なデータを渡した場合、元のデータがそのまま返される"""
        invalid_bytes = b"this is not an image"
        # 上限超過サイズにする（圧縮パスに入るため）
        large_invalid = invalid_bytes * (MAX_IMAGE_BYTES // len(invalid_bytes) + 1)
        result = preprocessor.preprocess(large_invalid)
        # 圧縮に失敗して元のデータが返される
        assert result == large_invalid

    def test_preprocess_color_image_stays_color(self, preprocessor):
        """カラー画像はカラーのまま返される（グレースケール変換なし）"""
        image_bytes = _create_test_image(color=True)
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        # カラー画像は3チャンネル
        assert len(decoded.shape) == 3
        assert decoded.shape[2] == 3
