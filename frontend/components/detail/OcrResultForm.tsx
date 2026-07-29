'use client';

import type { OcrDocument, OcrField } from '@/types';
import ConfidenceBadge from '@/components/common/ConfidenceBadge';
import ErrorList from '@/components/common/ErrorList';
import FieldEditor from './FieldEditor';

interface OcrResultFormProps {
  document: OcrDocument;
  onFieldUpdated: (document: OcrDocument) => void;
}

/**
 * OCR結果表示・編集フォームコンポーネント
 * 全フィールド一覧をテーブル形式で表示し、要確認フィールドにはFieldEditorを表示する
 */
export default function OcrResultForm({ document, onFieldUpdated }: OcrResultFormProps) {
  /**
   * フィールドの表示値を取得する
   * 修正値があればそちらを優先表示
   */
  const getDisplayValue = (field: OcrField): string => {
    if (field.corrected_value) return field.corrected_value;
    return field.value ?? '';
  };

  /**
   * フィールドがインライン編集を必要とするか判定
   * LOW confidenceかつ未確認の場合に編集UIを表示
   */
  const needsEditor = (field: OcrField): boolean => {
    return field.confidence_level === 'low' && !field.is_confirmed;
  };

  return (
    <div className="space-y-4">
      {/* バリデーションエラー表示 */}
      {document.validation_errors.length > 0 && (
        <ErrorList errors={document.validation_errors} />
      )}

      {/* フィールド一覧テーブル */}
      <div className="overflow-hidden rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th
                scope="col"
                className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500"
              >
                項目名
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500"
              >
                値
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500"
              >
                確信度
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500"
              >
                状態
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {document.fields.map((field) => (
              <tr key={field.field_name} className={needsEditor(field) ? 'bg-orange-50' : ''}>
                <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                  {field.field_name}
                </td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  <div>
                    <span>{getDisplayValue(field) || '—'}</span>
                    {/* 要確認フィールドにFieldEditorを表示 */}
                    {needsEditor(field) && (
                      <FieldEditor
                        fileId={document.file_id}
                        field={field}
                        onConfirmed={onFieldUpdated}
                      />
                    )}
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm">
                  <ConfidenceBadge
                    level={field.confidence_level}
                    score={field.confidence_score}
                  />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm">
                  {field.is_confirmed ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                      確認済
                    </span>
                  ) : field.confidence_level === 'low' ? (
                    <span className="inline-flex items-center rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
                      要確認
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                      自動確定
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* フィールドが0件の場合 */}
      {document.fields.length === 0 && (
        <p className="py-4 text-center text-sm text-gray-500">
          抽出されたフィールドがありません
        </p>
      )}
    </div>
  );
}
