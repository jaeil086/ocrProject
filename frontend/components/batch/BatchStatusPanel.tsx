'use client';

import type { BatchStatusResponse } from '@/types';

interface BatchStatusPanelProps {
  status: BatchStatusResponse;
  onDownloadCsv: () => void;
  onDownloadZip: () => void;
}

/**
 * バッチ処理状況パネル
 * 上部に配置し、総ファイル数・完了・処理中・確認必要・失敗・待機中 + 進捗バーを表示
 */
export default function BatchStatusPanel({
  status,
  onDownloadCsv,
  onDownloadZip,
}: BatchStatusPanelProps) {
  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      {/* ヘッダー行 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-700">バッチ処理状況</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">
            最終更新: {formatDate(status.updated_at)}
          </span>
        </div>
      </div>

      {/* ステータスカード行 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
        {/* 総ファイル数 */}
        <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">総ファイル数</div>
            <div className="text-lg font-bold text-gray-800">{status.total_files}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>

        {/* 完了 */}
        <div className="flex items-center gap-2 bg-green-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">完了</div>
            <div className="text-lg font-bold text-green-700">{status.completed}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>

        {/* 処理中 */}
        <div className="flex items-center gap-2 bg-blue-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">処理中</div>
            <div className="text-lg font-bold text-blue-700">{status.processing}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>

        {/* 確認必要 */}
        <div className="flex items-center gap-2 bg-amber-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">確認必要</div>
            <div className="text-lg font-bold text-amber-700">{status.needs_review}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>

        {/* 失敗 */}
        <div className="flex items-center gap-2 bg-red-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">失敗</div>
            <div className="text-lg font-bold text-red-700">{status.failed}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>

        {/* 待機中 */}
        <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <div className="text-xs text-gray-500">待機中</div>
            <div className="text-lg font-bold text-slate-600">{status.queued}<span className="text-xs font-normal ml-0.5">件</span></div>
          </div>
        </div>
      </div>

      {/* 進捗バー + ダウンロードボタン */}
      <div className="flex items-center gap-4">
        {/* 進捗バー（シンプルな青一色） */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">全体進捗率</span>
            <span className="text-sm font-bold text-blue-700">{status.progress_percent}%</span>
          </div>
          <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${status.progress_percent}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1">
            <div className="text-xs text-gray-400">
              {status.completed + status.needs_review + status.failed} / {status.total_files} 件 処理完了
            </div>
            {status.processing > 0 && (
              <div className="flex items-center gap-1 text-xs text-blue-600">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                {status.processing}件 処理中...
              </div>
            )}
          </div>
        </div>

        {/* ダウンロードボタン */}
        <div className="flex flex-col gap-2">
          <button
            onClick={onDownloadCsv}
            disabled={status.completed + status.needs_review === 0}
            className="flex items-center gap-2 bg-green-600 text-white text-xs font-medium px-4 py-2 rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            全体結果CSVダウンロード
          </button>
          <button
            onClick={onDownloadZip}
            disabled={status.total_files === 0}
            className="flex items-center gap-2 bg-blue-600 text-white text-xs font-medium px-4 py-2 rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
            </svg>
            全原本PDFダウンロード（ZIP）
          </button>
        </div>
      </div>
    </div>
  );
}
