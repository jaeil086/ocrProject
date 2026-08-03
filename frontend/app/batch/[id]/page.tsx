'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import type { BatchStatusResponse, BatchFileItem } from '@/types';
import { getBatchStatus, reprocessFile, downloadBatchCsv, downloadBatchZip } from '@/lib/api';
import BatchStatusPanel from '@/components/batch/BatchStatusPanel';
import BatchFileList from '@/components/batch/BatchFileList';
import BatchFileDetail from '@/components/batch/BatchFileDetail';

// ポーリング間隔（ミリ秒）
const POLL_INTERVAL = 3000;

/**
 * OCRバッチ処理管理画面
 * レイアウト:
 *   上部: バッチ処理状況パネル（ステータスカード + 進捗バー + ダウンロード）
 *   下部左: ファイル一覧
 *   下部右: ファイル詳細（PDFプレビュー / OCR結果 / チェック結果 / 処理ログ）
 */
export default function BatchPage() {
  const params = useParams();
  const batchId = params.id as string;

  const [status, setStatus] = useState<BatchStatusResponse | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // バッチ状況取得
  const fetchStatus = useCallback(async () => {
    try {
      const data = await getBatchStatus(batchId);
      setStatus(data);
      setError(null);

      // 初回ロード時に最初のファイルを自動選択
      if (!selectedFileId && data.files.length > 0) {
        setSelectedFileId(data.files[0].file_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'ステータスの取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, [batchId, selectedFileId]);

  // 初回ロードとポーリング
  useEffect(() => {
    fetchStatus();

    pollingRef.current = setInterval(fetchStatus, POLL_INTERVAL);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [fetchStatus]);

  // 処理完了時にポーリング停止
  useEffect(() => {
    if (status && (status.status === 'completed' || status.status === 'partial')) {
      if (status.processing === 0 && status.queued === 0) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    }
  }, [status]);

  // 再処理ハンドラー
  const handleReprocess = async (fileId: string) => {
    try {
      await reprocessFile(batchId, fileId);
      // ポーリング再開（停止していた場合）
      if (!pollingRef.current) {
        pollingRef.current = setInterval(fetchStatus, POLL_INTERVAL);
      }
      // 即座にステータス更新
      await fetchStatus();
    } catch (e) {
      alert(e instanceof Error ? e.message : '再処理の開始に失敗しました');
    }
  };

  // ダウンロードハンドラー
  const handleDownloadCsv = async () => {
    try {
      await downloadBatchCsv(batchId);
    } catch (e) {
      alert(e instanceof Error ? e.message : 'CSVダウンロードに失敗しました');
    }
  };

  const handleDownloadZip = async () => {
    try {
      await downloadBatchZip(batchId);
    } catch (e) {
      alert(e instanceof Error ? e.message : 'ZIPダウンロードに失敗しました');
    }
  };

  // 手動更新
  const handleRefresh = () => {
    fetchStatus();
  };

  // 選択中のファイル
  const selectedFile: BatchFileItem | null =
    status?.files.find((f) => f.file_id === selectedFileId) || null;

  // ローディング
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
          <span className="text-sm text-gray-600">バッチ処理状況を読み込み中...</span>
        </div>
      </div>
    );
  }

  // エラー
  if (error && !status) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="rounded-md bg-red-50 p-6 max-w-md">
          <div className="flex items-center gap-3">
            <svg className="h-6 w-6 text-red-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <div>
              <h3 className="text-sm font-medium text-red-800">エラー</h3>
              <p className="mt-1 text-sm text-red-700">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-bold text-gray-800">OCRバッチ処理管理</h1>
          </div>
          <div className="text-xs text-gray-400">
            バッチID: {batchId}
          </div>
        </div>
      </header>

      {/* メインコンテンツ */}
      <main className="max-w-[1600px] mx-auto px-6 py-4 space-y-4">
        {/* 上部: バッチ処理状況パネル */}
        <BatchStatusPanel
          status={status}
          onDownloadCsv={handleDownloadCsv}
          onDownloadZip={handleDownloadZip}
          onRefresh={handleRefresh}
        />

        {/* 下部: ファイル一覧 + ファイル詳細 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ minHeight: 'calc(100vh - 280px)' }}>
          {/* 左側: ファイル一覧 */}
          <div className="lg:col-span-5 xl:col-span-4">
            <BatchFileList
              files={status.files}
              selectedFileId={selectedFileId}
              onSelectFile={setSelectedFileId}
            />
          </div>

          {/* 右側: ファイル詳細 */}
          <div className="lg:col-span-7 xl:col-span-8">
            {selectedFile ? (
              <BatchFileDetail
                file={selectedFile}
                batchId={batchId}
                onReprocess={handleReprocess}
              />
            ) : (
              <div className="bg-white border border-gray-200 rounded-xl shadow-sm flex items-center justify-center h-full min-h-[400px]">
                <p className="text-sm text-gray-400">ファイルを選択してください</p>
              </div>
            )}
          </div>
        </div>

        {/* ファイル名ルール説明 */}
        <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 rounded-lg text-xs text-blue-700">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>
            ファイル名のルール：｛連番3桁｝_｛委託者番号｝_｛契約者番号｝.pdf　例）001_11137_10110.pdf
          </span>
        </div>
      </main>
    </div>
  );
}
