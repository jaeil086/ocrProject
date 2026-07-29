'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import FileDropzone from '@/components/upload/FileDropzone';
import UploadProgress from '@/components/upload/UploadProgress';
import StatusBadge from '@/components/common/StatusBadge';
import { uploadFiles } from '@/lib/api';
import type { UploadResponse } from '@/types';

/**
 * アップロード画面
 * FileDropzoneとUploadProgressを統合し、処理完了後に結果画面へ遷移する
 */
export default function UploadPage() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [results, setResults] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('アップロード中...');

  // ファイル選択ハンドラー
  const handleFilesSelected = (files: File[]) => {
    setSelectedFiles(files);
    setResults(null);
    setError(null);
  };

  // アップロード実行ハンドラー
  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setError(null);
    setUploadStatus('アップロード中...');

    try {
      setUploadStatus('OCR処理中...');
      const response = await uploadFiles(selectedFiles);
      setResults(response);
      setUploadStatus('完了');

      // 単一ファイルの場合は直接結果画面へ遷移
      if (response.files.length === 1) {
        router.push(`/result/${response.files[0].file_id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'エラーが発生しました');
    } finally {
      setIsUploading(false);
    }
  };

  // ファイル選択リセット
  const handleReset = () => {
    setSelectedFiles([]);
    setResults(null);
    setError(null);
  };

  return (
    <div className="flex flex-col items-center py-8">
      <h2 className="text-2xl font-semibold mb-6">口座振替依頼書 OCR処理</h2>

      {/* ドロップゾーン（結果未表示時のみ） */}
      {!results && (
        <div className="w-full max-w-xl">
          <FileDropzone onFilesSelected={handleFilesSelected} />
        </div>
      )}

      {/* 選択済みファイル一覧 */}
      {selectedFiles.length > 0 && !isUploading && !results && (
        <div className="w-full max-w-xl mt-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2">
            選択済みファイル（{selectedFiles.length}件）
          </h3>
          <ul className="space-y-1">
            {selectedFiles.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                className="flex items-center text-sm text-gray-600 bg-white rounded px-3 py-2 border border-gray-200"
              >
                <svg
                  className="w-4 h-4 mr-2 text-red-500 flex-shrink-0"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                  aria-hidden="true"
                >
                  <path d="M4 18h12a2 2 0 002-2V6l-4-4H4a2 2 0 00-2 2v12a2 2 0 002 2zm8-14l4 4h-4V4z" />
                </svg>
                <span className="truncate">{file.name}</span>
                <span className="ml-auto text-xs text-gray-400">
                  {(file.size / 1024).toFixed(0)} KB
                </span>
              </li>
            ))}
          </ul>

          {/* アップロードボタン */}
          <button
            onClick={handleUpload}
            className="mt-4 w-full bg-blue-600 text-white font-medium py-2.5 px-4 rounded-lg hover:bg-blue-700 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            アップロード開始
          </button>
        </div>
      )}

      {/* 進捗表示 */}
      {isUploading && (
        <div className="w-full max-w-xl">
          <UploadProgress isUploading={true} status={uploadStatus} />
        </div>
      )}

      {/* エラー表示 */}
      {error && (
        <div
          className="w-full max-w-xl mt-4 p-4 bg-red-50 border border-red-200 rounded-lg"
          role="alert"
        >
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={handleReset}
            className="mt-2 text-sm text-red-600 underline hover:text-red-800"
          >
            やり直す
          </button>
        </div>
      )}

      {/* 複数ファイルの結果一覧 */}
      {results && results.files.length > 1 && (
        <div className="w-full max-w-xl mt-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            処理結果（{results.total_count}件）
          </h3>
          <ul className="space-y-2">
            {results.files.map((file) => (
              <li key={file.file_id}>
                <button
                  onClick={() => router.push(`/result/${file.file_id}`)}
                  className="w-full flex items-center justify-between bg-white rounded-lg px-4 py-3 border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all duration-200 text-left"
                >
                  <div className="flex items-center min-w-0">
                    <svg
                      className="w-4 h-4 mr-2 text-red-500 flex-shrink-0"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                    >
                      <path d="M4 18h12a2 2 0 002-2V6l-4-4H4a2 2 0 00-2 2v12a2 2 0 002 2zm8-14l4 4h-4V4z" />
                    </svg>
                    <span className="text-sm text-gray-700 truncate">
                      {file.original_filename}
                    </span>
                  </div>
                  <StatusBadge status={file.status} />
                </button>
              </li>
            ))}
          </ul>

          {/* 新規アップロードボタン */}
          <button
            onClick={handleReset}
            className="mt-4 w-full border border-gray-300 text-gray-700 font-medium py-2 px-4 rounded-lg hover:bg-gray-50 transition-colors duration-200"
          >
            新規アップロード
          </button>
        </div>
      )}
    </div>
  );
}
