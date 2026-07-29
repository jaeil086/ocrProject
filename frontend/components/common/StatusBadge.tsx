import { DocumentStatus } from '@/types';

interface StatusBadgeProps {
  status: DocumentStatus;
}

// ステータスごとの色クラスマッピング
const statusColorMap: Record<DocumentStatus, string> = {
  normal: 'bg-green-100 text-green-800',
  deficient: 'bg-red-100 text-red-800',
  needs_review: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  uploading: 'bg-gray-100 text-gray-800',
};

// ステータスごとの日本語ラベルマッピング
const statusLabelMap: Record<DocumentStatus, string> = {
  normal: '正常',
  deficient: '不備',
  needs_review: '要確認',
  processing: '処理中',
  uploading: 'アップロード中',
};

/**
 * ステータスバッジコンポーネント
 * 書類の処理ステータスを色分けして表示する
 */
export default function StatusBadge({ status }: StatusBadgeProps) {
  const colorClass = statusColorMap[status];
  const label = statusLabelMap[status];

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass}`}
    >
      {label}
    </span>
  );
}
