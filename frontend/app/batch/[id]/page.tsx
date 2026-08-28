'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import type { BatchStatusResponse, BatchFileItem } from '@/types';
import { getBatchStatus, reprocessFile, downloadBatchCsv, downloadBatchZip } from '@/lib/api';
import BatchStatusPanel from '@/components/batch/BatchStatusPanel';
import BatchFileList from '@/components/batch/BatchFileList';
import BatchFileDetail from '@/components/batch/BatchFileDetail';

// ポーリング間隔（ミリ秒）— 処理中は1.5秒、完了後は停止
const POLL_INTERVAL = 1500;

/**
 * OCRバッチ処理管理画面
 * レイアウト:
 *   上部: バッチ処理状況パネル（ステータスカード + 進捗バー + ダウンロード）
 *   下部左: ファイル一覧
 *   下部右: ファイル詳細（PDFプレビュー / OCR結果 + チェック結果 / 処理ログ）
 *
 * 初回ロード時もすぐにUIを表示し、ポーリングで状態をリアルタイム反映する。
 */
export default function BatchPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const batchId = params.id as string;
  const initialTotal = parseInt(searchParams.get('total') || '0', 10);

  // sessionStorageから初期ファイル一覧を取得（アップロード直後に即座に表示するため）
  const getInitialFiles = (): import('@/types').BatchFileItem[] => {
    if (typeof window === 'undefined') return [];
    const stored = sessionStorage.getItem(`batch_initial_${batchId}`);
    if (stored) {
      sessionStorage.removeItem(`batch_initial_${batchId}`);
      try {
        return JSON.parse(stored);
      } catch {
        return [];
      }
    }
    return [];
  };

  const initialFiles = getInitialFiles();

  // 初期状態: sessionStorageから取得したファイル一覧で即座にUI表示
  const [status, setStatus] = useState<BatchStatusResponse>({
    batch_id: batchId,
    status: 'processing',
    total_files: initialTotal || initialFiles.length,
    completed: 0,
    processing: 0,
    needs_review: 0,
    failed: 0,
    queued: initialTotal || initialFiles.length,
    progress_percent: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    files: initialFiles,
  });
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initialLoaded, setInitialLoaded] = useState(false);
  // 進捗率が減少しないよう最大値を保持する
  const maxProgressRef = useRef(0);

  // ポーリング制御用ref
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingActive = useRef(true);

  // ポーリングが必要かどうか判定
  const shouldStopPolling = useCallback((data: BatchStatusResponse) => {
    if (data.status === 'completed' || data.status === 'partial') {
      return data.processing === 0 && data.queued === 0;
    }
    return false;
  }, []);

  // バッチ状況取得（単発）
  const fetchStatus = useCallback(async () => {
    try {
      const data = await getBatchStatus(batchId);
      // 進捗率が減少しないよう最大値で保持する
      if (data.progress_percent >= maxProgressRef.current) {
        maxProgressRef.current = data.progress_percent;
      } else {
        data.progress_percent = maxProgressRef.current;
      }
      setStatus(data);
      setError(null);
      setInitialLoaded(true);

      // 初回ロード時に最初のファイルを自動選択
      setSelectedFileId((prev) => {
        if (!prev && data.files.length > 0) {
          return data.files[0].file_id;
        }
        return prev;
      });

      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'ステータスの取得に失敗しました');
      setInitialLoaded(true);
      return null;
    }
  }, [batchId]);

  // setTimeoutチェーン方式のポーリング
  useEffect(() => {
    isPollingActive.current = true;

    const poll = async () => {
      if (!isPollingActive.current) return;

      const data = await fetchStatus();

      // 処理完了ならポーリング停止
      if (data && shouldStopPolling(data)) {
        isPollingActive.current = false;
        return;
      }

      // まだアクティブなら次のポーリングを予約
      if (isPollingActive.current) {
        pollingRef.current = setTimeout(poll, POLL_INTERVAL);
      }
    };

    // 初回実行
    poll();

    return () => {
      isPollingActive.current = false;
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [fetchStatus, shouldStopPolling]);

  // 再処理ハンドラー
  const handleReprocess = async (fileId: string) => {
    try {
      await reprocessFile(batchId, fileId);
      // 再処理開始時に進捗最大値をリセット（バーが下がるのを許可する）
      maxProgressRef.current = 0;
      // ポーリング再開（停止していた場合）
      if (!isPollingActive.current) {
        isPollingActive.current = true;
        const poll = async () => {
          if (!isPollingActive.current) return;
          const data = await fetchStatus();
          if (data && shouldStopPolling(data)) {
            isPollingActive.current = false;
            return;
          }
          if (isPollingActive.current) {
            pollingRef.current = setTimeout(poll, POLL_INTERVAL);
          }
        };
        poll();
      } else {
        await fetchStatus();
      }
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

  // 手動更新は不要（自動ポーリングで充分なため削除済み）

  // 選択中のファイル
  const selectedFile: BatchFileItem | null =
    status.files.find((f) => f.file_id === selectedFileId) || null;

  // 致命的エラー（初回取得すら失敗）
  if (error && !initialLoaded) {
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
                onRefresh={fetchStatus}
              />
            ) : (
              <div className="bg-white border border-gray-200 rounded-xl shadow-sm flex items-center justify-center h-full min-h-[400px]">
                <div className="text-center">
                  <p className="text-sm text-gray-400">
                    左のファイル一覧からファイルを選択してください
                  </p>
                </div>
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
            ｜複数ページPDFは自動的にページ単位で分割されます（例：sample_p1.pdf, sample_p2.pdf）
          </span>
        </div>
      </main>
    </div>
  );
}
