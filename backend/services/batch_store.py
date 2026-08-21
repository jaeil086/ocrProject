"""
BatchStore: バッチジョブのインメモリ管理

バッチジョブ全体の状態管理と各ファイルのステータス追跡を行う。
将来的にDB化を見据えた設計。
"""

from datetime import datetime
from typing import Optional

from backend.models.enums import BatchFileStatus, BatchJobStatus
from backend.models.schemas import BatchFileItem, BatchJob, BatchLogEntry


class BatchStore:
    """バッチジョブのインメモリストア"""

    def __init__(self) -> None:
        self._jobs: dict[str, BatchJob] = {}

    def create_job(self, batch_id: str, total_files: int) -> BatchJob:
        """新規バッチジョブを作成する"""
        job = BatchJob(
            batch_id=batch_id,
            status=BatchJobStatus.UPLOADING,
            total_files=total_files,
        )
        self._jobs[batch_id] = job
        return job

    def get_job(self, batch_id: str) -> Optional[BatchJob]:
        """バッチジョブを取得する"""
        return self._jobs.get(batch_id)

    def add_file(self, batch_id: str, file_item: BatchFileItem) -> None:
        """バッチジョブにファイル項目を追加する"""
        job = self._jobs.get(batch_id)
        if job:
            job.files.append(file_item)
            job.updated_at = datetime.now()

    def update_file_status(
        self,
        batch_id: str,
        file_id: str,
        status: BatchFileStatus,
        error_message: Optional[str] = None,
        consignor_number: Optional[str] = None,
        contract_number: Optional[str] = None,
    ) -> Optional[BatchFileItem]:
        """ファイルのステータスを更新する"""
        job = self._jobs.get(batch_id)
        if not job:
            return None

        for file_item in job.files:
            if file_item.file_id == file_id:
                file_item.status = status
                file_item.updated_at = datetime.now()

                if error_message is not None:
                    file_item.error_message = error_message

                if consignor_number is not None:
                    file_item.consignor_number = consignor_number

                if contract_number is not None:
                    file_item.contract_number = contract_number

                if status == BatchFileStatus.PROCESSING:
                    file_item.processing_started_at = datetime.now()
                elif status in (
                    BatchFileStatus.COMPLETED,
                    BatchFileStatus.NEEDS_REVIEW,
                    BatchFileStatus.FAILED,
                ):
                    file_item.processing_completed_at = datetime.now()

                # ジョブ全体のステータスを再計算
                self._recalculate_job_status(job)
                return file_item

        return None

    def add_file_log(
        self,
        batch_id: str,
        file_id: str,
        message: str,
        level: str = "info",
    ) -> None:
        """ファイルに処理ログを追加する"""
        job = self._jobs.get(batch_id)
        if not job:
            return

        for file_item in job.files:
            if file_item.file_id == file_id:
                log_entry = BatchLogEntry(
                    timestamp=datetime.now(),
                    message=message,
                    level=level,
                )
                file_item.logs.append(log_entry)
                break

    def update_file_progress(
        self,
        batch_id: str,
        file_id: str,
        progress: int,
    ) -> None:
        """ファイルの処理進捗を更新する（0〜100）"""
        job = self._jobs.get(batch_id)
        if not job:
            return

        for file_item in job.files:
            if file_item.file_id == file_id:
                file_item.progress = min(100, max(0, progress))
                file_item.updated_at = datetime.now()
                break

    def update_file_batch_filename(
        self,
        batch_id: str,
        file_id: str,
        batch_filename: str,
    ) -> None:
        """バッチ命名規則に基づくファイル名を更新する"""
        job = self._jobs.get(batch_id)
        if not job:
            return

        for file_item in job.files:
            if file_item.file_id == file_id:
                file_item.batch_filename = batch_filename
                file_item.updated_at = datetime.now()
                break

    def start_processing(self, batch_id: str) -> None:
        """バッチジョブの処理を開始状態にする"""
        job = self._jobs.get(batch_id)
        if job:
            job.status = BatchJobStatus.PROCESSING
            job.updated_at = datetime.now()

    def get_file_item(
        self, batch_id: str, file_id: str
    ) -> Optional[BatchFileItem]:
        """特定ファイル項目を取得する"""
        job = self._jobs.get(batch_id)
        if not job:
            return None

        for file_item in job.files:
            if file_item.file_id == file_id:
                return file_item
        return None

    def list_jobs(self) -> list[BatchJob]:
        """全バッチジョブをリストする（最新順）"""
        return sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )

    def set_s3_keys(
        self,
        batch_id: str,
        output_key: str | None = None,
        archive_key: str | None = None,
    ) -> None:
        """S3に保存したオブジェクトキーをジョブに記録する"""
        job = self._jobs.get(batch_id)
        if not job:
            return
        if output_key is not None:
            job.s3_output_key = output_key
        if archive_key is not None:
            job.s3_archive_key = archive_key
        job.updated_at = datetime.now()

    def _recalculate_job_status(self, job: BatchJob) -> None:
        """ジョブ全体のステータスを再計算する"""
        if not job.files:
            return

        all_done = all(
            f.status
            in (
                BatchFileStatus.COMPLETED,
                BatchFileStatus.NEEDS_REVIEW,
                BatchFileStatus.FAILED,
            )
            for f in job.files
        )

        if all_done:
            has_failed = any(
                f.status == BatchFileStatus.FAILED for f in job.files
            )
            has_review = any(
                f.status == BatchFileStatus.NEEDS_REVIEW for f in job.files
            )
            if has_failed or has_review:
                job.status = BatchJobStatus.PARTIAL
            else:
                job.status = BatchJobStatus.COMPLETED
        else:
            job.status = BatchJobStatus.PROCESSING

        job.updated_at = datetime.now()


# グローバルストア（アプリケーションライフサイクルに紐づくシングルトン）
batch_store = BatchStore()
