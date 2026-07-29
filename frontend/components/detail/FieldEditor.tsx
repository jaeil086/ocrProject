'use client';

import { useState } from 'react';
import { updateField, getResult } from '@/lib/api';
import type { OcrField, OcrDocument } from '@/types';

interface FieldEditorProps {
  fileId: string;
  field: OcrField;
  onConfirmed: (updatedDocument: OcrDocument) => void;
}

/**
 * 要確認フィールドの修正入力UIコンポーネント
 * 元の認識値を表示し、修正値を入力して確認ボタンで送信する
 */
export default function FieldEditor({ fileId, field, onConfirmed }: FieldEditorProps) {
  const [correctedValue, setCorrectedValue] = useState(field.value ?? '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    if (!correctedValue.trim()) {
      setError('修正値を入力してください');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // フィールド修正APIを呼び出し
      await updateField(fileId, field.field_name, correctedValue.trim());
      // 最新のドキュメントを取得して親に通知
      const updatedDocument = await getResult(fileId);
      onConfirmed(updatedDocument);
    } catch (e) {
      setError('修正の保存に失敗しました。再度お試しください。');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mt-2 rounded-md border border-orange-200 bg-orange-50 p-3">
      {/* 元の認識値表示 */}
      <div className="mb-2 text-sm">
        <span className="font-medium text-gray-700">認識値: </span>
        <span className="text-gray-900">{field.value ?? '（空）'}</span>
      </div>

      {/* 修正値入力 */}
      <div className="flex items-center gap-2">
        <label htmlFor={`field-editor-${field.field_name}`} className="sr-only">
          {field.field_name}の修正値
        </label>
        <input
          id={`field-editor-${field.field_name}`}
          type="text"
          value={correctedValue}
          onChange={(e) => setCorrectedValue(e.target.value)}
          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="修正値を入力"
          disabled={isSubmitting}
        />
        <button
          type="button"
          onClick={handleConfirm}
          disabled={isSubmitting}
          className="inline-flex items-center rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? '保存中...' : '確認'}
        </button>
      </div>

      {/* エラー表示 */}
      {error && (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      )}
    </div>
  );
}
