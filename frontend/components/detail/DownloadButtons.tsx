'use client';

import { useState } from 'react';
import { downloadCsv, downloadPdf } from '@/lib/api';
import type { OcrDocument } from '@/types';

interface DownloadButtonsProps {
  document: OcrDocument;
}

/**
 * CSV/PDFダウンロードボタン
 * 全確認完了時のみアクティブになる
 *
 * ボタン無効条件:
 * - Confidence LOWのフィールドが未確認（is_confirmed === false）
 * - 目視確認項目が未チェック（is_checked === false）
 */
export default function DownloadButtons({ document }: DownloadButtonsProps) {
  const [downloadingCsv, setDownloadingCsv] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 全ての確認が完了しているかチェック
  const hasUnconfirmedLowFields = document.fields.some(
    (field) => field.confidence_level === 'low' && !field.is_confirmed
  );
  const hasUncheckedVisualChecks = document.visual_checks.some(
    (check) => !check.is_checked
  );
  const isDisabled = hasUnconfirmedLowFields || hasUncheckedVisualChecks;

  // CSVダウンロードハンドラ
  const handleCsvDownload = async () => {
    if (isDisabled) return;
    setDownloadingCsv(true);
    setError(null);

    try {
      await downloadCsv(document.file_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'CSVダウンロードに失敗しました');
    } finally {
      setDownloadingCsv(false);
    }
  };

  // PDFダウンロードハンドラ
  const handlePdfDownload = async () => {
    if (isDisabled) return;
    setDownloadingPdf(true);
    setError(null);

    try {
      await downloadPdf(document.file_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'PDFダウンロードに失敗しました');
    } finally {
      setDownloadingPdf(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">成果物ダウンロード</h3>

      {error && (
        <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 未確認警告 */}
      {isDisabled && (
        <div className="mb-3 p-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-700">
          全ての確認を完了してください
        </div>
      )}

      <div className="flex gap-3">
        {/* CSVダウンロードボタン */}
        <button
          onClick={handleCsvDownload}
          disabled={isDisabled || downloadingCsv}
          title={isDisabled ? '全ての確認を完了してください' : 'CSVファイルをダウンロード'}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            isDisabled
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-green-600 text-white hover:bg-green-700 active:bg-green-800'
          }`}
        >
          {downloadingCsv ? (
            <span>ダウンロード中...</span>
          ) : (
            <>
              <CsvIcon />
              <span>CSVダウンロード</span>
            </>
          )}
        </button>

        {/* PDFダウンロードボタン */}
        <button
          onClick={handlePdfDownload}
          disabled={isDisabled || downloadingPdf}
          title={isDisabled ? '全ての確認を完了してください' : 'リネーム済みPDFをダウンロード'}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            isDisabled
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800'
          }`}
        >
          {downloadingPdf ? (
            <span>ダウンロード中...</span>
          ) : (
            <>
              <PdfIcon />
              <span>PDFダウンロード</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// CSVアイコン（SVG）
function CsvIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  );
}

// PDFアイコン（SVG）
function PdfIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  );
}
