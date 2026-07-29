'use client';

import { useState } from 'react';
import { updateVisualCheck, getResult } from '@/lib/api';
import type { OcrDocument, VisualCheck, VisualCheckType } from '@/types';

interface VisualCheckListProps {
  document: OcrDocument;
  onUpdated: (document: OcrDocument) => void;
}

/**
 * 目視確認チェックリスト
 * 届出印、〇印選択、収納代行会社の確認チェックボックスを表示し、
 * 担当者が確認完了を記録する
 */
export default function VisualCheckList({ document, onUpdated }: VisualCheckListProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // チェックボックス変更ハンドラ
  const handleToggle = async (check: VisualCheck) => {
    setLoading(check.check_item);
    setError(null);

    try {
      // APIを呼び出して目視確認ステータスを更新
      await updateVisualCheck(
        document.file_id,
        check.check_item,
        !check.is_checked,
        '担当者'
      );

      // ドキュメント全体を再取得して親コンポーネントに通知
      const updated = await getResult(document.file_id);
      onUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新に失敗しました');
    } finally {
      setLoading(null);
    }
  };

  // 確認種別に応じたバッジの色を返す
  const getBadgeStyle = (checkType: VisualCheckType): string => {
    if (checkType === '確認者チェック必要') {
      return 'bg-orange-100 text-orange-800';
    }
    return 'bg-purple-100 text-purple-800';
  };

  if (document.visual_checks.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">目視確認項目</h3>

      {error && (
        <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <ul className="space-y-2">
        {document.visual_checks.map((check) => (
          <li
            key={check.check_item}
            className="flex items-center gap-3 p-2 rounded hover:bg-gray-50"
          >
            {/* チェックボックス */}
            <input
              type="checkbox"
              id={`visual-check-${check.check_item}`}
              checked={check.is_checked}
              disabled={loading === check.check_item}
              onChange={() => handleToggle(check)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
            />

            {/* 確認項目名 */}
            <label
              htmlFor={`visual-check-${check.check_item}`}
              className={`flex-1 text-sm cursor-pointer ${
                check.is_checked ? 'text-gray-500 line-through' : 'text-gray-900'
              }`}
            >
              {check.check_item}
            </label>

            {/* 確認種別バッジ */}
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getBadgeStyle(
                check.check_type
              )}`}
            >
              {check.check_type}
            </span>

            {/* ローディング表示 */}
            {loading === check.check_item && (
              <span className="text-xs text-gray-400">更新中...</span>
            )}
          </li>
        ))}
      </ul>

      {/* 確認進捗サマリー */}
      <div className="mt-3 pt-3 border-t border-gray-100">
        <p className="text-xs text-gray-500">
          確認済み: {document.visual_checks.filter((c) => c.is_checked).length} /{' '}
          {document.visual_checks.length}
        </p>
      </div>
    </div>
  );
}
