'use client';

import { useState, useEffect } from 'react';
import type { BatchFileItem, OcrDocument, OcrField } from '@/types';
import { getResult, downloadCsv, downloadPdf } from '@/lib/api';

interface BatchFileDetailProps {
  file: BatchFileItem;
  batchId: string;
  onReprocess: (fileId: string) => void;
}

type TabId = 'preview' | 'ocr' | 'check' | 'log';

/** チェック結果バッジ */
function CheckBadge({ field }: { field: OcrField }) {
  if (!field.value) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
        NG
      </span>
    );
  }
  if (field.confidence_level === 'low') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
        確認必要
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
      OK
    </span>
  );
}

/**
 * バッチファイル詳細コンポーネント
 * 右側パネル: PDFプレビュー・OCR結果・チェック結果・処理ログをタブで切り替え
 */
export default function BatchFileDetail({
  file,
  batchId,
  onReprocess,
}: BatchFileDetailProps) {
  const [activeTab, setActiveTab] = useState<TabId>('preview');
  const [document, setDocument] = useState<OcrDocument | null>(null);
  const [loading, setLoading] = useState(false);

  // ファイル選択変更時にOCR結果を取得
  useEffect(() => {
    if (file.status === 'completed' || file.status === 'needs_review') {
      setLoading(true);
      getResult(file.file_id)
        .then(setDocument)
        .catch(() => setDocument(null))
        .finally(() => setLoading(false));
    } else {
      setDocument(null);
    }
  }, [file.file_id, file.status]);

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

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: 'preview', label: '原本PDFプレビュー', icon: '📄' },
    { id: 'ocr', label: 'OCR抽出結果', icon: '🔍' },
    { id: 'check', label: 'チェック結果', icon: '✓' },
    { id: 'log', label: '処理ログ', icon: '📋' },
  ];

  // ステータスバッジ
  const statusConfig: Record<string, { label: string; className: string }> = {
    completed: { label: '完了', className: 'bg-green-100 text-green-700' },
    processing: { label: '処理中', className: 'bg-blue-100 text-blue-700' },
    queued: { label: '待機中', className: 'bg-slate-100 text-slate-600' },
    needs_review: { label: '確認必要', className: 'bg-amber-100 text-amber-700' },
    failed: { label: '失敗', className: 'bg-red-100 text-red-700' },
  };

  const canReprocess = file.status === 'failed' || file.status === 'needs_review';

  // OCR主要項目フィールド名リスト
  const mainFields = [
    '預金者氏名',
    '預金者フリガナ',
    '銀行名',
    '支店名',
    '預金種目',
    '口座番号',
    '銀行番号',
    '店番号',
    '振替日',
    '委託者番号',
    '契約者番号',
    '委託者名',
    '料金等の種類',
  ];

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm flex flex-col h-full">
      {/* ヘッダー: ファイル名 + ステータス */}
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span className="text-sm font-semibold text-gray-800">{file.batch_filename}</span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusConfig[file.status]?.className || ''}`}>
            {statusConfig[file.status]?.label || file.status}
          </span>
        </div>
        <span className="text-xs text-gray-400">
          最終更新: {formatDate(file.updated_at)}
        </span>
      </div>

      {/* タブヘッダー */}
      <div className="flex border-b border-gray-200">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-700 bg-blue-50/50'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <span aria-hidden="true">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* タブコンテンツ */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* PDFプレビュータブ */}
        {activeTab === 'preview' && (
          <div className="h-full min-h-[400px]">
            {file.status === 'queued' ? (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                処理待ちです
              </div>
            ) : (
              <iframe
                src={`/api/result/${file.file_id}/pdf-preview`}
                className="w-full h-full min-h-[500px] border border-gray-200 rounded-lg"
                title="PDFプレビュー"
              />
            )}
          </div>
        )}

        {/* OCR抽出結果タブ */}
        {activeTab === 'ocr' && (
          <div>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
              </div>
            ) : document ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-600 mb-3">OCR抽出結果（主要項目）</h4>
                <div className="space-y-1.5">
                  {mainFields.map((fieldName) => {
                    const field = document.fields.find((f) => f.field_name === fieldName);
                    const value = field?.corrected_value || field?.value || '-';
                    return (
                      <div key={fieldName} className="flex items-center text-xs border-b border-gray-50 py-1.5">
                        <span className="w-28 text-gray-500 flex-shrink-0">{fieldName}</span>
                        <span className="flex-1 text-gray-800 font-medium">{value}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-400 text-sm py-12">
                {file.status === 'failed'
                  ? 'OCR処理が失敗しました'
                  : file.status === 'processing'
                  ? 'OCR処理中...'
                  : '結果がまだありません'}
              </div>
            )}
          </div>
        )}

        {/* チェック結果タブ */}
        {activeTab === 'check' && (
          <div>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
              </div>
            ) : document ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-600 mb-3">チェック結果（主要項目）</h4>
                <div className="grid grid-cols-2 gap-2">
                  {mainFields.map((fieldName) => {
                    const field = document.fields.find((f) => f.field_name === fieldName);
                    return (
                      <div key={fieldName} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                        <span className="text-xs text-gray-600">{fieldName}</span>
                        {field ? <CheckBadge field={field} /> : (
                          <span className="text-xs text-gray-400">-</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-400 text-sm py-12">
                チェック結果がまだありません
              </div>
            )}
          </div>
        )}

        {/* 処理ログタブ */}
        {activeTab === 'log' && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-3">処理ログ</h4>
            {file.logs.length > 0 ? (
              <div className="space-y-1">
                {file.logs.map((log, idx) => (
                  <div
                    key={idx}
                    className={`flex items-start gap-2 text-xs px-3 py-2 rounded ${
                      log.level === 'error'
                        ? 'bg-red-50 text-red-700'
                        : log.level === 'warning'
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-gray-50 text-gray-600'
                    }`}
                  >
                    <span className="text-[10px] text-gray-400 whitespace-nowrap flex-shrink-0">
                      {formatDate(log.timestamp)}
                    </span>
                    <span className="flex-1">{log.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-400 text-sm py-12">
                ログがまだありません
              </div>
            )}
          </div>
        )}
      </div>

      {/* フッター: 個別ダウンロード + 再処理 */}
      <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={() => downloadCsv(file.file_id)}
            disabled={!document}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-green-50 text-green-700 hover:bg-green-100 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            このファイルのCSVダウンロード
          </button>
          <button
            onClick={() => downloadPdf(file.file_id)}
            disabled={file.status === 'queued'}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            このファイルのPDFダウンロード
          </button>
        </div>

        {canReprocess && (
          <button
            onClick={() => onReprocess(file.file_id)}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-orange-50 text-orange-700 hover:bg-orange-100 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            再処理
          </button>
        )}
      </div>
    </div>
  );
}
