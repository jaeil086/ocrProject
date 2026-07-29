"""
ImagePreprocessorのユニットテスト

テスト画像を動的に生成し、前処理パイプラインの動作を検証する。
"""

import cv2
import numpy as np
import pytest

from backend.services.image_preprocessor import ImagePreprocessor


@pytest.fixture
def preprocessor():
    """ImagePreprocessorインスタンスを返すフィクスチャ"""
    return ImagePreprocessor()


def _create_test_image(width: int = 300, height: int = 200, color: bool = True) -> bytes:
    """テスト用のカラー画像をPNGバイナリとして生成する"""
    if color:
        # 白背景にテキスト風の黒線を描画
        img = np.ones((height, width, 3), dtype=np.uint8) * 255
        # 水平線（テキスト行を模倣）
        cv2.line(img, (20, 50), (280, 50), (0, 0, 0), 2)
        cv2.line(img, (20, 100), (280, 100), (0, 0, 0), 2)
        cv2.line(img, (20, 150), (280, 150), (0, 0, 0), 2)
    else:
        img = np.ones((height, width), dtype=np.uint8) * 255
        cv2.line(img, (20, 50), (280, 50), 0, 2)

    _, buffer = cv2.imencode(".png", img)
    return buffer.tobytes()


def _create_skewed_image(angle_deg: float = 5.0) -> bytes:
    """傾いた画像を生成する（傾き補正テスト用）"""
    width, height = 400, 300
    img = np.ones((height, width, 3), dtype=np.uint8) * 255

    # 水平線を多数描画（Hough変換で検出可能）
    for y in range(50, 250, 30):
        cv2.line(img, (30, y), (370, y), (0, 0, 0), 2)

    # 画像を回転させて傾きを付与
    center = (width // 2, height // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    skewed = cv2.warpAffine(img, rotation_matrix, (width, height), borderValue=(255, 255, 255))

    _, buffer = cv2.imencode(".png", skewed)
    return buffer.tobytes()


class TestImagePreprocessor:
    """ImagePreprocessorのテストスイート"""

    def test_preprocess_returns_bytes(self, preprocessor):
        """preprocess()がbytes型を返すことを確認"""
        image_bytes = _create_test_image()
        result = preprocessor.preprocess(image_bytes)
        assert isinstance(result, bytes)

    def test_preprocess_returns_valid_png(self, preprocessor):
        """preprocess()の出力がデコード可能なPNG画像であることを確認"""
        image_bytes = _create_test_image()
        result = preprocessor.preprocess(image_bytes)

        # 出力をデコードして有効な画像であることを確認
        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        assert decoded is not None

    def test_preprocess_output_is_grayscale(self, preprocessor):
        """preprocess()の出力がグレースケール（1チャンネル）であることを確認"""
        image_bytes = _create_test_image(color=True)
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        # 二値化後の画像は1チャンネル
        assert len(decoded.shape) == 2

    def test_preprocess_output_is_binary(self, preprocessor):
        """preprocess()の出力が二値画像（0と255のみ）であることを確認"""
        image_bytes = _create_test_image()
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        # 大津の二値化により、ピクセル値は0か255のいずれか
        unique_values = np.unique(decoded)
        assert all(v in [0, 255] for v in unique_values)

    def test_preprocess_preserves_dimensions(self, preprocessor):
        """preprocess()が画像のサイズを保持することを確認"""
        width, height = 300, 200
        image_bytes = _create_test_image(width=width, height=height)
        result = preprocessor.preprocess(image_bytes)

        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        assert decoded.shape == (height, width)

    def test_deskew_with_no_lines(self, preprocessor):
        """_deskew()に直線のない画像を渡した場合、元の画像が返ることを確認"""
        # 単色画像（直線なし）
        img = np.ones((100, 100), dtype=np.uint8) * 128
        result = preprocessor._deskew(img)

        # 元の画像と同一であること
        np.testing.assert_array_equal(result, img)

    def test_deskew_with_horizontal_lines(self, preprocessor):
        """_deskew()が水平線を含む画像に対して正常に動作することを確認"""
        # 水平線のみの画像（傾きなし）
        img = np.ones((200, 300), dtype=np.uint8) * 255
        cv2.line(img, (20, 100), (280, 100), 0, 2)
        cv2.line(img, (20, 150), (280, 150), 0, 2)

        result = preprocessor._deskew(img)
        # サイズが保持されること
        assert result.shape == img.shape

    def test_preprocess_with_skewed_image(self, preprocessor):
        """傾いた画像に対してpreprocess()が正常に動作することを確認"""
        image_bytes = _create_skewed_image(angle_deg=3.0)
        result = preprocessor.preprocess(image_bytes)

        # 有効なPNG出力
        assert isinstance(result, bytes)
        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        assert decoded is not None
