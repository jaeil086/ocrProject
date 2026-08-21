"""
S3ストレージサービス

入力PDF・出力CSV・アーカイブZIPをAWS S3に保存するサービス。
バケット: cheiru-ocr-storage
  - 00_input/   : 入力PDFをZIP化して保存
  - 01_output/  : 全体結果Excelファイル保存
  - 02_archive/ : 全原本PDFのZIPファイル保存

ファイル名形式: {batch_id}_{YYYYMMDD_HHMMSS}.{拡張子}
"""

import io
import logging
import urllib.parse
import zipfile
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from backend.config import (
    AWS_REGION,
    S3_ARCHIVE_PREFIX,
    S3_BUCKET_NAME,
    S3_INPUT_PREFIX,
    S3_OUTPUT_PREFIX,
)

logger = logging.getLogger(__name__)


class S3Storage:
    """S3ストレージ操作クラス"""

    def __init__(self) -> None:
        self._client = boto3.client("s3", region_name=AWS_REGION)

    def _generate_s3_key(self, prefix: str, batch_id: str, extension: str) -> str:
        """S3オブジェクトキーを生成する

        形式: {prefix}/{batch_id}_{YYYYMMDD_HHMMSS}.{extension}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{batch_id}_{timestamp}.{extension}"
        return f"{prefix}/{filename}"

    def upload_input_zip(
        self, batch_id: str, pdf_files: list[tuple[str, bytes]]
    ) -> str:
        """入力PDFファイルをZIP化してS3にアップロードする

        Args:
            batch_id: バッチジョブID
            pdf_files: (ファイル名, PDFバイナリ) のリスト

        Returns:
            アップロードしたS3オブジェクトキー
        """
        # メモリ上でZIPファイルを作成
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, pdf_bytes in pdf_files:
                zf.writestr(filename, pdf_bytes)
        buffer.seek(0)

        s3_key = self._generate_s3_key(S3_INPUT_PREFIX, batch_id, "zip")

        try:
            self._client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=buffer.getvalue(),
                ContentType="application/zip",
            )
            logger.info(f"[S3] 入力ZIP保存完了: s3://{S3_BUCKET_NAME}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"[S3] 入力ZIPアップロード失敗: {e}")
            raise

    def upload_output_excel(self, batch_id: str, excel_bytes: bytes) -> str:
        """全体結果Excelファイルを S3にアップロードする

        Args:
            batch_id: バッチジョブID
            excel_bytes: Excelバイナリデータ

        Returns:
            アップロードしたS3オブジェクトキー
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"RESULT_{batch_id}_{timestamp}.xlsx"
        s3_key = f"{S3_OUTPUT_PREFIX}/{filename}"

        try:
            self._client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=excel_bytes,
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            logger.info(f"[S3] 結果Excel保存完了: s3://{S3_BUCKET_NAME}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"[S3] 結果Excelアップロード失敗: {e}")
            raise

    def upload_archive_zip(self, batch_id: str, zip_bytes: bytes) -> str:
        """全原本PDFのZIPファイルをS3にアップロードする

        Args:
            batch_id: バッチジョブID
            zip_bytes: ZIPバイナリデータ

        Returns:
            アップロードしたS3オブジェクトキー
        """
        s3_key = self._generate_s3_key(S3_ARCHIVE_PREFIX, batch_id, "zip")

        try:
            self._client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=zip_bytes,
                ContentType="application/zip",
            )
            logger.info(f"[S3] アーカイブZIP保存完了: s3://{S3_BUCKET_NAME}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"[S3] アーカイブZIPアップロード失敗: {e}")
            raise

    def generate_presigned_url(
        self, s3_key: str, expires_in: int = 600, filename: str | None = None
    ) -> str:
        """S3オブジェクトのPre-signed URLを生成する

        Args:
            s3_key: S3オブジェクトキー
            expires_in: URL有効期限（秒）。デフォルト600秒（10分）
            filename: ダウンロード時のファイル名（指定時にContent-Dispositionヘッダーを付与）

        Returns:
            Pre-signed URL文字列
        """
        params = {
            "Bucket": S3_BUCKET_NAME,
            "Key": s3_key,
        }
        if filename:
            encoded_filename = urllib.parse.quote(filename)
            params["ResponseContentDisposition"] = (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            )

        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            logger.info(f"[S3] Pre-signed URL生成: {s3_key} (有効期限: {expires_in}秒)")
            return url
        except ClientError as e:
            logger.error(f"[S3] Pre-signed URL生成失敗: {e}")
            raise


# グローバルインスタンス（シングルトン）
s3_storage = S3Storage()
