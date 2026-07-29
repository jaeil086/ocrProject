'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { getResult } from '@/lib/api';
import type { OcrDocument } from '@/types';
import PdfPreview from '@/components/detail/PdfPreview';
import StatusBadge from '@/components/common/StatusBadge';
import ErrorList from '@/components/common/ErrorList';

/**
 * OCR結果確認画面ページ
 * 左側にPDFプレビュー、右側にOCR結果・操作パネルを配置
 * Requirements: 13.1, 13.5
 */
export default function ResultPage() {
  const params = useParams();
  const fileId = params.id as string;

  const [document, setDocument] = useState<OcrDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchResult() {
      try {
        const result = await getResult(fileId);
        setDocument(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : '結果の取得に失敗しました');
      } finally {
        setLoading(false);
      }
    }
    fetchResult();
  }, [fileId]);

  // ローディング表示
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
          <span className="text-sm text-gray-600">読み込み中...</span>
        </div>
      </div>
    );
  }

  // エラー表示
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="rounded-md bg-red-50 p-6 max-w-md">
          <div className="flex items-center gap-3">
            <svg
              className="h-6 w-6 text-red-400 flex-shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
              />
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

  // データ未取得
  if (!document) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-gray-500">データが見つかりません</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
      {/* 左カラム: PDFプレビュー */}
      <div className="lg:sticky lg:top-6 lg:self-start">
        <PdfPreview fileId={fileId} />
      </div>

      {/* 右カラム: OCR結果・操作パネル */}
      <div className="space-y-6">
        {/* ヘッダー: ファイル名 + ステータス */}
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900 truncate">
            {document.original_filename}
          </h2>
          <StatusBadge status={document.status} />
        </div>

        {/* バリデーションエラー一覧 */}
        {document.validation_errors.length > 0 && (
          <ErrorList errors={document.validation_errors} />
        )}

        {/* OCR結果表示・編集フォーム（タスク10.2で実装） */}
        <div className="rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">OCR抽出結果</h3>
          <div className="space-y-2">
            {document.fields.map((field) => (
              <div
                key={field.field_name}
                className="flex items-center justify-between py-2 border-b border-gray-100 last:border-b-0"
              >
                <span className="text-sm text-gray-600">{field.field_name}</span>
                <span className="text-sm font-medium text-gray-900">
                  {field.corrected_value || field.value || '—'}
                </span>
              </div>
            ))}
            {document.fields.length === 0 && (
              <p className="text-sm text-gray-400">抽出フィールドがありません</p>
            )}
          </div>
        </div>

        {/* 目視確認チェックリスト */}
        {document.visual_checks.length > 0 && (
          <div className="rounded-lg border border-gray-200 p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-3">目視確認項目</h3>
            <div className="space-y-2">
              {document.visual_checks.map((check) => (
                <div
                  key={check.check_item}
                  className="flex items-center gap-3 py-1"
                >
                  <input
                    type="checkbox"
                    checked={check.is_checked}
                    onChange={async () => {
                      try {
                        const { updateVisualCheck } = await import('@/lib/api');
                        await updateVisualCheck(
                          fileId,
                          check.check_item,
                          !check.is_checked,
                          '担当者'
                        );
                        // ローカル状態を更新
                        setDocument((prev) => {
                          if (!prev) return prev;
                          return {
                            ...prev,
                            visual_checks: prev.visual_checks.map((c) =>
                              c.check_item === check.check_item
                                ? { ...c, is_checked: !c.is_checked }
                                : c
                            ),
                          };
                        });
                      } catch (e) {
                        console.error('目視確認の更新に失敗:', e);
                      }
                    }}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 cursor-pointer"
                  />
                  <span className="text-sm text-gray-700">{check.check_item}</span>
                  <span className="text-xs text-gray-400">{check.check_type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ダウンロードボタン（タスク10.3で実装） */}
        <div className="flex gap-3">
          <a
            href={`/api/result/${fileId}/csv`}
            download
            className="inline-flex items-center rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
          >
            CSVダウンロード
          </a>
          <a
            href={`/api/result/${fileId}/pdf`}
            download
            className="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            PDFダウンロード
          </a>
        </div>
      </div>
    </div>
  );
}
