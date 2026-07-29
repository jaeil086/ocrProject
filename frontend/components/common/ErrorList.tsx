import { ValidationError } from '@/types';

interface ErrorListProps {
  errors: ValidationError[];
}

/**
 * バリデーションエラー一覧表示コンポーネント
 * 各エラーのフィールド名、エラー種別、メッセージを表示する
 */
export default function ErrorList({ errors }: ErrorListProps) {
  if (errors.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md bg-red-50 p-4">
      <div className="flex">
        <div className="flex-shrink-0">
          {/* エラーアイコン */}
          <svg
            className="h-5 w-5 text-red-400"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <div className="ml-3">
          <h3 className="text-sm font-medium text-red-800">
            {errors.length}件のエラーがあります
          </h3>
          <div className="mt-2">
            <ul className="list-disc space-y-1 pl-5 text-sm text-red-700">
              {errors.map((error, index) => (
                <li key={`${error.field_name}-${index}`}>
                  <span className="font-medium">{error.field_name}</span>
                  <span className="mx-1 inline-flex items-center rounded bg-red-200 px-1.5 py-0.5 text-xs font-medium text-red-800">
                    {error.error_type}
                  </span>
                  <span>{error.message}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
