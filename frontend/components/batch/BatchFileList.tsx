'use client';

import { useState, useMemo } from 'react';
import type { BatchFileItem, BatchFileStatus } from '@/types';

interface BatchFileListProps {
  files: BatchFileItem[];
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
}

/** ステータスバッジ表示（アニメーション付き） */
function StatusBadge({ status }: { status: BatchFileStatus }) {
  const config: Record<BatchFileStatus, { label: string; className: string; icon: string; animate?: boolean }> = {
    completed: {
      label: '完了',
      className: 'bg-green-100 text-green-700',
      icon: '✅',
    },
    processing: {
      label: '処理中',
      className: 'bg-blue-100 text-blue-700',
      icon: '🔄',
      animate: true,
    },
    queued: {
      label: '待機中',
      className: 'bg-slate-100 text-slate-600',
      icon: '⏸',
    },
    needs_review: {
      label: '確認必要',
      className: 'bg-amber-100 text-amber-700',
      icon: '⚠',
    },
    failed: {
      label: '失敗',
      className: 'bg-red-100 text-red-700',
      icon: '❌',
    },
  };

  const c = config[status];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${c.className}`}>
      <span aria-hidden="true" className={c.animate ? 'animate-spin' : ''}>{c.icon}</span>
      {c.label}
    </span>
  );
}

/** ファイル行の進捗インジケーター（progress値に連動） */
function FileProgressBar({ status, progress }: { status: BatchFileStatus; progress: number }) {
  if (status === 'processing') {
    return (
      <div className="w-full h-1.5 bg-blue-100 rounded-full overflow-hidden mt-1">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    );
  }
  if (status === 'queued') {
    return (
      <div className="w-full h-1.5 bg-gray-100 rounded-full mt-1">
        <div className="h-full bg-gray-300 rounded-full" style={{ width: '0%' }} />
      </div>
    );
  }
  if (status === 'completed') {
    return (
      <div className="w-full h-1.5 bg-green-100 rounded-full mt-1">
        <div className="h-full bg-green-500 rounded-full transition-all duration-500" style={{ width: '100%' }} />
      </div>
    );
  }
  if (status === 'needs_review') {
    return (
      <div className="w-full h-1.5 bg-amber-100 rounded-full mt-1">
        <div className="h-full bg-amber-500 rounded-full transition-all duration-500" style={{ width: '100%' }} />
      </div>
    );
  }
  if (status === 'failed') {
    return (
      <div className="w-full h-1.5 bg-red-100 rounded-full mt-1">
        <div className="h-full bg-red-500 rounded-full transition-all duration-500" style={{ width: '100%' }} />
      </div>
    );
  }
  return null;
}

const ITEMS_PER_PAGE = 10;

/**
 * バッチファイル一覧コンポーネント
 * 全ファイルを最初から表示し、各ファイルのステータスがリアルタイムで変化する
 */
export default function BatchFileList({
  files,
  selectedFileId,
  onSelectFile,
}: BatchFileListProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<BatchFileStatus | 'all'>('all');
  const [currentPage, setCurrentPage] = useState(1);

  // フィルタリング
  const filteredFiles = useMemo(() => {
    let result = files;

    // ステータスフィルタ
    if (statusFilter !== 'all') {
      result = result.filter((f) => f.status === statusFilter);
    }

    // 検索フィルタ（ファイル名・委託者番号・契約者番号）
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (f) =>
          f.batch_filename.toLowerCase().includes(q) ||
          f.original_filename.toLowerCase().includes(q) ||
          (f.consignor_number && f.consignor_number.includes(q)) ||
          (f.contract_number && f.contract_number.includes(q))
      );
    }

    return result;
  }, [files, statusFilter, searchQuery]);

  // ページネーション
  const totalPages = Math.ceil(filteredFiles.length / ITEMS_PER_PAGE);
  const paginatedFiles = filteredFiles.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  // ページ変更時にリセット
  const handleFilterChange = (filter: BatchFileStatus | 'all') => {
    setStatusFilter(filter);
    setCurrentPage(1);
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setCurrentPage(1);
  };

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
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm flex flex-col h-full">
      {/* ヘッダー */}
      <div className="px-4 py-3 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-700">
          ファイル一覧（{files.length}件）
        </h3>
      </div>

      {/* 検索・フィルタ */}
      <div className="px-4 py-3 border-b border-gray-100 space-y-2">
        {/* 検索バー */}
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="ファイル名・委託者番号・契約者番号で検索"
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* ステータスフィルタ */}
        <select
          value={statusFilter}
          onChange={(e) => handleFilterChange(e.target.value as BatchFileStatus | 'all')}
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">すべての状態</option>
          <option value="completed">✅ 完了</option>
          <option value="processing">🔄 処理中</option>
          <option value="needs_review">⚠ 確認必要</option>
          <option value="failed">❌ 失敗</option>
          <option value="queued">⏸ 待機中</option>
        </select>
      </div>

      {/* テーブル */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-500">No.</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500">ファイル名</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500">委託者番号</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500">契約者番号</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500">状態</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500">最終更新</th>
            </tr>
          </thead>
          <tbody>
            {paginatedFiles.map((file) => (
              <tr
                key={file.file_id}
                onClick={() => onSelectFile(file.file_id)}
                className={`cursor-pointer border-b border-gray-50 transition-all duration-300 ${
                  selectedFileId === file.file_id
                    ? 'bg-blue-50 border-l-2 border-l-blue-500'
                    : file.status === 'processing'
                    ? 'bg-blue-50/30 hover:bg-blue-50/60'
                    : 'hover:bg-gray-50'
                }`}
              >
                <td className="px-3 pt-2.5 pb-1 text-gray-600">
                  {String(file.seq_number).padStart(3, '0')}
                </td>
                <td className="px-3 pt-2.5 pb-1 text-gray-800 font-medium truncate max-w-[140px]" title={file.batch_filename}>
                  <div>{file.batch_filename.includes('unknown') ? file.original_filename : file.batch_filename}</div>
                  <FileProgressBar status={file.status} progress={file.progress} />
                </td>
                <td className="px-3 pt-2.5 pb-1 text-gray-600">
                  {file.consignor_number || '-'}
                </td>
                <td className="px-3 pt-2.5 pb-1 text-gray-600">
                  {file.contract_number || '-'}
                </td>
                <td className="px-3 pt-2.5 pb-1">
                  <StatusBadge status={file.status} />
                </td>
                <td className="px-3 pt-2.5 pb-1 text-gray-400 whitespace-nowrap">
                  {formatDate(file.updated_at)}
                </td>
              </tr>
            ))}
            {paginatedFiles.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-gray-400">
                  該当するファイルがありません
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ページネーション */}
      {totalPages > 1 && (
        <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="px-2 py-1 text-xs border border-gray-200 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="前のページ"
            >
              &lt;
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              let pageNum: number;
              if (totalPages <= 5) {
                pageNum = i + 1;
              } else if (currentPage <= 3) {
                pageNum = i + 1;
              } else if (currentPage >= totalPages - 2) {
                pageNum = totalPages - 4 + i;
              } else {
                pageNum = currentPage - 2 + i;
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  className={`px-2.5 py-1 text-xs rounded ${
                    currentPage === pageNum
                      ? 'bg-blue-600 text-white'
                      : 'border border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="px-2 py-1 text-xs border border-gray-200 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="次のページ"
            >
              &gt;
            </button>
          </div>
          <span className="text-xs text-gray-400">
            {(currentPage - 1) * ITEMS_PER_PAGE + 1}-{Math.min(currentPage * ITEMS_PER_PAGE, filteredFiles.length)} / {filteredFiles.length} 件
          </span>
        </div>
      )}

      {/* フッター: ステータス凡例 */}
      <div className="px-4 py-2 border-t border-gray-100 flex flex-wrap gap-3 text-[10px] text-gray-400">
        <span>● <span className="text-green-600">完了</span>: 正常に処理が完了</span>
        <span>● <span className="text-blue-600">処理中</span>: 処理中です</span>
        <span>● <span className="text-amber-600">確認必要</span>: 内容の確認が必要</span>
        <span>● <span className="text-red-600">失敗</span>: 処理に失敗</span>
        <span>● <span className="text-slate-500">待機中</span>: 処理待ち</span>
      </div>
    </div>
  );
}
