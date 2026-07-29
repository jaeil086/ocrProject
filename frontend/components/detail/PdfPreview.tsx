'use client';

import { useState } from 'react';

interface PdfPreviewProps {
  /** ファイルID（PDFプレビュー取得用） */
  fileId: string;
}

/**
 * PDFプレビューコンポーネント
 * 原本PDFをiframeで画面上に表示する
 * API: GET /api/result/{fileId}/pdf からPDFを取得して表示
 */
export default function PdfPreview({ fileId }: PdfPreviewProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // PDFプレビュー用URL（inline表示エンドポイント）
  const pdfUrl = `/api/result/${fileId}/pdf-preview`;

  return (
    <div className="flex flex-col h-full">
      <h3 className="text-sm font-medium text-gray-700 mb-2">原本PDFプレビュー</h3>
      <div className="relative flex-1 min-h-[600px] border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
        {/* ローディング表示 */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
              <span className="text-sm text-gray-500">PDF読み込み中...</span>
            </div>
          </div>
        )}

        {/* エラー表示 */}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="flex flex-col items-center gap-2 text-center px-4">
              <svg
                className="h-10 w-10 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                />
              </svg>
              <p className="text-sm text-gray-500">
                PDFの読み込みに失敗しました
              </p>
            </div>
          </div>
        )}

        {/* PDF表示（iframe） */}
        <iframe
          src={pdfUrl}
          className="w-full h-full min-h-[600px]"
          title="原本PDFプレビュー"
          onLoad={() => setLoading(false)}
          onError={() => {
            setLoading(false);
            setError(true);
          }}
        />
      </div>
    </div>
  );
}
