'use client';

interface UploadProgressProps {
  isUploading: boolean;
  progress?: number;
  status?: string;
}

/**
 * アップロード・処理進捗バー表示コンポーネント
 * アップロード中およびOCR処理中の進捗状況を表示する
 */
export default function UploadProgress({
  isUploading,
  progress,
  status = 'アップロード中...',
}: UploadProgressProps) {
  if (!isUploading) return null;

  return (
    <div className="w-full mt-4" role="status" aria-live="polite">
      {/* ステータステキスト */}
      <div className="flex items-center mb-2">
        {/* スピナー */}
        <svg
          className="animate-spin h-4 w-4 mr-2 text-blue-600"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        <span className="text-sm font-medium text-gray-700">{status}</span>
      </div>

      {/* プログレスバー */}
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
          style={{ width: progress != null ? `${progress}%` : '100%' }}
          role="progressbar"
          aria-valuenow={progress ?? undefined}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="処理進捗"
        >
          {/* プログレスが未定義の場合はアニメーション（indeterminate） */}
          {progress == null && (
            <div className="h-full w-1/3 bg-blue-400 rounded-full animate-pulse" />
          )}
        </div>
      </div>

      {/* 進捗パーセント表示 */}
      {progress != null && (
        <p className="mt-1 text-xs text-gray-500 text-right">{progress}%</p>
      )}
    </div>
  );
}
