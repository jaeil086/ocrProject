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
 */
export default function UploadPage() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [results, setResults] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('アップロード中...');

  const handleFilesSelected = (files: File[]) => {
    setSelectedFiles(files);
    setResults(null);
    setError(null);
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setError(null);
    setUploadStatus('OCR処理中...');

    try {
      const response = await uploadFiles(selectedFiles);
      setResults(response);
      setUploadStatus('完了');

      if (response.files.length === 1) {
        router.push(`/result/${response.files[0].file_id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'エラーが発生しました');
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = () => {
    setSelectedFiles([]);
    setResults(null);
    setError(null);
  };

  return (
    <div className="flex flex-col items-center">
      {/* メインセクション — 背景画像を全体に敷く */}
      <section className="w-full flex-1 relative min-h-[calc(100vh-120px)]">
        {/* 背景画像（全画面） */}
        <div className="absolute inset-0">
          <img
            src="/bg-pattern.png"
            alt=""
            className="w-full h-full object-cover"
            aria-hidden="true"
          />
        </div>

        {/* コンテンツ */}
        <div className="relative z-10 max-w-4xl mx-auto px-6 py-12">
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              口座振替依頼書 OCR処理
            </h2>
            <p className="text-sm text-gray-500">
              PDF形式の口座振替依頼書をアップロードしてください
            </p>
          </div>

        {/* ドロップゾーン */}
        {!results && (
          <div className="w-full max-w-lg mx-auto">
            <FileDropzone onFilesSelected={handleFilesSelected} />
          </div>
        )}

        {/* 選択済みファイル一覧 */}
        {selectedFiles.length > 0 && !isUploading && !results && (
          <div className="w-full max-w-lg mx-auto mt-6">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              選択済みファイル（{selectedFiles.length}件）
            </h3>
            <ul className="space-y-1">
              {selectedFiles.map((file, index) => (
                <li
                  key={`${file.name}-${index}`}
                  className="flex items-center text-sm text-gray-600 bg-white rounded-lg px-4 py-2.5 border border-gray-200"
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

            <button
              onClick={handleUpload}
              className="mt-4 w-full bg-blue-600 text-white font-medium py-3 px-4 rounded-lg hover:bg-blue-700 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              アップロード開始
            </button>
          </div>
        )}

        {/* 進捗表示 */}
        {isUploading && (
          <div className="w-full max-w-lg mx-auto mt-6">
            <UploadProgress isUploading={true} status={uploadStatus} />
          </div>
        )}

        {/* エラー表示 */}
        {error && (
          <div
            className="w-full max-w-lg mx-auto mt-6 p-4 bg-red-50 border border-red-200 rounded-lg"
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

        {/* 複数ファイル結果一覧 */}
        {results && results.files.length > 1 && (
          <div className="w-full max-w-lg mx-auto mt-6">
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

            <button
              onClick={handleReset}
              className="mt-4 w-full border border-gray-300 text-gray-700 font-medium py-2.5 px-4 rounded-lg hover:bg-gray-50 transition-colors duration-200"
            >
              新規アップロード
            </button>
          </div>
        )}
        </div>

        {/* 処理の流れセクション（背景画像内） */}
        {!results && !isUploading && selectedFiles.length === 0 && (
          <div className="relative z-10 max-w-4xl mx-auto px-6 pt-8 pb-12">
            <h3 className="text-center text-sm font-semibold text-gray-600 mb-8">
              処理の流れ
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              {/* Step 1 */}
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-white/80 backdrop-blur flex items-center justify-center mb-3 shadow-sm">
                  <svg className="w-7 h-7 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-800">1. PDFアップロード</p>
                <p className="text-xs text-gray-500 mt-1">口座振替依頼書を<br/>アップロードします</p>
              </div>

              {/* Step 2 */}
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-white/80 backdrop-blur flex items-center justify-center mb-3 shadow-sm">
                  <svg className="w-7 h-7 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-800">2. OCR解析</p>
                <p className="text-xs text-gray-500 mt-1">Claude OCRが<br/>文字を読み取ります</p>
              </div>

              {/* Step 3 */}
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-white/80 backdrop-blur flex items-center justify-center mb-3 shadow-sm">
                  <svg className="w-7 h-7 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-800">3. データ抽出</p>
                <p className="text-xs text-gray-500 mt-1">AIが必要な情報を<br/>自動で抽出します</p>
              </div>

              {/* Step 4 */}
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-white/80 backdrop-blur flex items-center justify-center mb-3 shadow-sm">
                  <svg className="w-7 h-7 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-800">4. CSV出力</p>
                <p className="text-xs text-gray-500 mt-1">抽出結果をCSVで<br/>ダウンロードできます</p>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
