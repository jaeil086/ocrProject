import { ConfidenceLevel } from '@/types';

interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
  score: number;
}

/**
 * Confidence Score表示バッジコンポーネント
 * HIGH/LOWを視覚的に区別して表示する
 */
export default function ConfidenceBadge({ level, score }: ConfidenceBadgeProps) {
  const isHigh = level === 'high';

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${
        isHigh ? 'text-green-600' : 'text-orange-600'
      }`}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          isHigh ? 'bg-green-500' : 'bg-orange-500'
        }`}
        aria-hidden="true"
      />
      {score.toFixed(1)}%
    </span>
  );
}
