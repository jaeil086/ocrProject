'use client';

import { useCallback, useState, useRef } from 'react';

interface FileDropzoneProps {
  onFilesSelected: (files: File[]) => void;
  /** 既存の選択済みファイル（追加モード用） */
  existingFiles?: File[];
}

/**
 * ドラッグ&ドロップ + ファイル選択コンポーネント
 * PDF形式のみ受け付ける。ファイル追加時は既存ファイルを維持する。
 */
export default function FileDropzone({ onFilesSelected, existingFiles = [] }: FileDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // PDFファイルのみフィルタリングする
  const filterPdfFiles = useCallback((fileList: FileList | File[]): File[] => {
    const files = Array.from(fileList);
    const pdfFiles = files.filter(
      (file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    );

    if (pdfFiles.length < files.length) {
      setError('PDF形式のファイルを選択してください');
    } else {
      setError(null);
    }

    return pdfFiles;
  }, []);

  // 重複ファイルを除外してマージする
  const mergeFiles = useCallback((newFiles: File[]): File[] => {
    const existingNames = new Set(existingFiles.map((f) => f.name + '_' + f.size));
    const uniqueNewFiles = newFiles.filter(
      (f) => !existingNames.has(f.name + '_' + f.size)
    );
    return [...existingFiles, ...uniqueNewFiles];
  }, [existingFiles]);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const pdfFiles = filterPdfFiles(e.dataTransfer.files);
      if (pdfFiles.length > 0) {
        onFilesSelected(mergeFiles(pdfFiles));
      }
    },
    [filterPdfFiles, mergeFiles, onFilesSelected]
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        const pdfFiles = filterPdfFiles(e.target.files);
        if (pdfFiles.length > 0) {
          onFilesSelected(mergeFiles(pdfFiles));
        }
      }
      // input値をリセット（同じファイルを再選択可能にする）
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    },
    [filterPdfFiles, mergeFiles, onFilesSelected]
  );

  const handleClick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  return (
    <div className="w-full">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleClick();
          }
        }}
        aria-label="PDFファイルをドラッグ&ドロップまたはクリックして選択"
        className={`
          flex flex-col items-center justify-center w-full h-64 
          border-2 border-dashed rounded-xl cursor-pointer
          transition-colors duration-200
          ${
            isDragOver
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100'
          }
        `}
      >
        {/* アップロードアイコン */}
        <svg
          className={`w-10 h-10 mb-3 ${isDragOver ? 'text-blue-500' : 'text-gray-400'}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p className="mb-1 text-sm text-gray-600">
          <span className="font-semibold">クリックしてファイルを選択</span>
          　またはドラッグ&ドロップ
        </p>
        <p className="text-xs text-gray-500">PDF形式のみ（複数選択可）</p>

        {/* ファイルを選択ボタン */}
        <div className="mt-4">
          <span className="inline-flex items-center gap-2 bg-blue-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-blue-700 transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            ファイルを選択
          </span>
        </div>
      </div>

      {/* 非表示のファイル入力 */}
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        multiple
        onChange={handleFileChange}
        className="hidden"
        aria-hidden="true"
      />

      {/* エラーメッセージ */}
      {error && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
