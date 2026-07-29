'use client';

import { useEffect, useState } from 'react';

interface UploadProgressProps {
  isUploading: boolean;
  progress?: number;
  status?: string;
}

/**
 * アップロード・処理進捗バー表示コンポーネント
 * 2段階OCR処理の進捗を段階的に表示する
 */
export default function UploadProgress({
  isUploading,
  progress: externalProgress,
  status: externalStatus,
}: UploadProgressProps) {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('アップロード中...');
  const [step, setStep] = useState(0);

  // 処理ステップの定義
  const steps = [
    { label: 'PDFアップロード中...', target: 15, duration: 2000 },
    { label: 'PDF→画像変換中...', target: 25, duration: 3000 },
    { label: 'Step1: 全テキスト読み取り中...', target: 55, duration: 20000 },
    { label: 'Step2: フィールド抽出中...', target: 85, duration: 20000 },
    { label: 'バリデーション処理中...', target: 95, duration: 3000 },
  ];

  useEffect(() => {
    if (!isUploading) {
      setProgress(0);
      setStep(0);
      setStatus('アップロード中...');
      return;
    }

    // 外部からprogressが指定された場合はそちらを使用
    if (externalProgress != null) {
      setProgress(externalProgress);
      if (externalStatus) setStatus(externalStatus);
      return;
    }

    // 時間ベースのシミュレーション
    let currentStep = 0;
    let currentProgress = 0;

    const advanceStep = () => {
      if (currentStep >= steps.length) return;

      const { label, target, duration } = steps[currentStep];
      setStatus(label);

      // このステップ内で徐々に進行
      const startProgress = currentProgress;
      const increment = (target - startProgress) / (duration / 200);
      
      const interval = setInterval(() => {
        currentProgress += increment;
        if (currentProgress >= target) {
          currentProgress = target;
          clearInterval(interval);
          currentStep++;
          // 次のステップへ
          setTimeout(advanceStep, 500);
        }
        setProgress(Math.min(Math.round(currentProgress), 99));
      }, 200);

      return () => clearInterval(interval);
    };

    advanceStep();
  }, [isUploading, externalProgress, externalStatus]);

  if (!isUploading) return null;

  return (
    <div className="w-full mt-4 bg-white/90 backdrop-blur rounded-xl p-5 shadow-sm border border-gray-100" role="status" aria-live="polite">
      {/* ステータステキスト */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center">
          <svg
            className="animate-spin h-4 w-4 mr-2 text-blue-600"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className="text-sm font-medium text-gray-700">{status}</span>
        </div>
        <span className="text-sm font-semibold text-blue-600">{progress}%</span>
      </div>

      {/* プログレスバー */}
      <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out"
          style={{ width: `${progress}%` }}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="処理進捗"
        />
      </div>

      {/* ステップ表示 */}
      <div className="mt-3 flex justify-between text-xs text-gray-400">
        <span>アップロード</span>
        <span>OCR読み取り</span>
        <span>データ抽出</span>
        <span>完了</span>
      </div>
    </div>
  );
}
