'use client';

import { useState, useEffect } from 'react';
import type { BatchFileItem, OcrDocument, OcrField, MasterMatchInfo } from '@/types';
import { getResult, downloadCsv, downloadPdf } from '@/lib/api';

interface BatchFileDetailProps {
  file: BatchFileItem;
  batchId: string;
  onReprocess: (fileId: string) => void;
}

type TabId = 'preview_ocr' | 'log';

/** チェック結果インラインバッジ */
function InlineCheckBadge({ field, allFields }: { field: OcrField; allFields?: OcrField[] }) {
  // お届出印金融機関は「あり」/「なし」で判定
  if (field.field_name === 'お届出印金融機関') {
    if (field.value === 'あり') {
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-600">
          OK
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-600">
        NG
      </span>
    );
  }

  // 銀行系フィールドとゆうちょ系フィールドの排他判定
  const bankFieldNames = ['銀行名', '支店名', '預金種目', '口座番号', '銀行番号', '店番号'];
  const yuchoFieldNames = ['ゆうちょ記号', 'ゆうちょ番号'];

  if (!field.value && allFields) {
    const hasYucho = yuchoFieldNames.some(
      (fn) => allFields.find((f) => f.field_name === fn)?.value
    );
    const hasBank = bankFieldNames.some(
      (fn) => allFields.find((f) => f.field_name === fn)?.value
    );

    // 排他: 相手側に記入があり自分側が空欄 → 正常（「-」表示）
    if (bankFieldNames.includes(field.field_name) && hasYucho) {
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-400">
          -
        </span>
      );
    }
    if (yuchoFieldNames.includes(field.field_name) && hasBank) {
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-400">
          -
        </span>
      );
    }
  }

  if (!field.value) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-600">
        NG
      </span>
    );
  }
  // 銀行名で種別未選択（x）の場合はNG
  if (field.field_name === '銀行名' && field.value.includes('（x）')) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-600">
        NG
      </span>
    );
  }
  // マスター交差検証不一致の場合は「確認必要」（銀行名/銀行番号/支店名/店番号）
  if (field.master_match?.cross_check_status === 'mismatch') {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-600">
          確認必要
        </span>
        <span className="text-[10px] text-amber-500">
          コード不一致
        </span>
      </span>
    );
  }
  // マスター照合がng（マスターに存在しない）の場合
  if (field.master_match?.match_status === 'ng') {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-600">
          NG
        </span>
        <span className="text-[10px] text-red-400">
          マスタ不一致
        </span>
      </span>
    );
  }
  if (field.confidence_level === 'low') {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-600">
          確認必要
        </span>
        <span className="text-[10px] text-amber-500">
          {Math.round(field.confidence_score)}%
        </span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-600">
      OK
    </span>
  );
}

/**
 * マスター照合情報のインライン表示
 * 銀行名・銀行番号・支店名・店番号フィールドでmaster_matchが存在する場合に表示
 */
function MasterMatchDetail({ masterMatch }: { masterMatch: MasterMatchInfo }) {
  if (masterMatch.match_status === 'unverified') {
    return null;
  }

  // 交差検証不一致の場合: マスター候補を表示
  if (masterMatch.cross_check_status === 'mismatch') {
    return (
      <div className="space-y-0.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px]">
          {masterMatch.master_value && (
            <span className="text-gray-500">
              マスタ: <span className="font-medium text-amber-700">{masterMatch.master_value}</span>
            </span>
          )}
          {masterMatch.master_code && (
            <span className="text-gray-500">
              コード: <span className="font-mono font-medium text-amber-700">{masterMatch.master_code}</span>
            </span>
          )}
          <span className="inline-flex items-center px-1 py-0.5 rounded bg-red-50 text-red-600 font-bold">
            コード不一致
          </span>
        </div>
        {/* 候補リスト（番号逆引きと名前マッチで改行分割） */}
        {masterMatch.candidates.length > 0 && (() => {
          const codeCandidates = masterMatch.candidates.filter(c => c.name.includes('（番号'));
          const nameCandidates = masterMatch.candidates.filter(c => !c.name.includes('（番号'));
          return (
            <div className="text-[10px] space-y-0.5">
              {codeCandidates.length > 0 && (
                <div className="text-gray-500">
                  番号から: {codeCandidates.slice(0, 2).map((c, i) => (
                    <span key={i} className="mr-1.5">
                      <span className="font-medium text-blue-700">{c.name}</span>
                      <span className="font-mono text-gray-400"> [{c.code}]</span>
                    </span>
                  ))}
                </div>
              )}
              {nameCandidates.length > 0 && (
                <div className="text-gray-400">
                  候補: {nameCandidates.slice(0, 5).map((c, i) => (
                    <span key={i} className="mr-1.5">
                      <span className="text-gray-600">{c.name}</span>
                      <span className="font-mono text-gray-400"> [{c.code}]</span>
                      <span className="text-gray-400"> {Math.round(c.score)}%</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })()}
      </div>
    );
  }

  // 通常のマスター照合表示
  return (
    <div className="space-y-0.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px]">
        {masterMatch.master_value && (
          <span className="text-gray-500">
            マスタ: <span className="font-medium text-gray-700">{masterMatch.master_value}</span>
          </span>
        )}
        {masterMatch.master_code && (
          <span className="text-gray-500">
            コード: <span className="font-mono font-medium text-gray-700">{masterMatch.master_code}</span>
          </span>
        )}
        {masterMatch.match_status === 'ok' && masterMatch.match_score > 0 && (
          <span className="text-green-600">
            一致率: {Math.round(masterMatch.match_score)}%
          </span>
        )}
        {masterMatch.match_status === 'needs_review' && masterMatch.match_score > 0 && (
          <span className="text-amber-600">
            一致率: {Math.round(masterMatch.match_score)}%
          </span>
        )}
      </div>
      {/* 候補リスト（needs_review / ng の場合） */}
      {masterMatch.match_status !== 'ok' && masterMatch.candidates.length > 0 && (() => {
        const codeCandidates = masterMatch.candidates.filter(c => c.name.includes('（番号'));
        const nameCandidates = masterMatch.candidates.filter(c => !c.name.includes('（番号'));
        return (
          <div className="text-[10px] space-y-0.5">
            {codeCandidates.length > 0 && (
              <div className="text-gray-500">
                番号から: {codeCandidates.slice(0, 2).map((c, i) => (
                  <span key={i} className="mr-1.5">
                    <span className="font-medium text-blue-700">{c.name}</span>
                    <span className="font-mono text-gray-400"> [{c.code}]</span>
                  </span>
                ))}
              </div>
            )}
            {nameCandidates.length > 0 && (
              <div className="text-gray-400">
                候補: {nameCandidates.slice(0, 5).map((c, i) => (
                  <span key={i} className="mr-1.5">
                    <span className="text-gray-600">{c.name}</span>
                    <span className="font-mono text-gray-400"> [{c.code}]</span>
                    <span className="text-gray-400"> {Math.round(c.score)}%</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

/**
 * 金融機関グループのマスター照合結果を3パターンで表示
 * パターン1: 名前OK + コード不一致 → 「名前は正しい。正しいコードは○○」
 * パターン2: コードOK + 名前不一致 → 「コード○○は△△です」
 * パターン3: 両方不一致 → 名前の候補リストを表示
 */
function FinancialGroupMatchDetail({
  primaryMatch,
  codeMatch,
  nameLabel,
  codeLabel,
}: {
  primaryMatch: MasterMatchInfo | null | undefined;
  codeMatch: MasterMatchInfo | null | undefined;
  nameLabel: string;
  codeLabel: string;
}) {
  // 判定: 名前のマスター照合がOKか
  const nameIsOk = primaryMatch?.match_status === 'ok';
  // 判定: コードのマスター照合がOKか（OCRコードがマスターに存在する）
  const codeIsOk = codeMatch?.match_status === 'ok' && !codeMatch?.cross_check_status;
  // 交差検証不一致があるか
  const hasCrossCheckMismatch = primaryMatch?.cross_check_status === 'mismatch'
    || codeMatch?.cross_check_status === 'mismatch';

  // パターン1: 名前OK + コード不一致（名前は正しく読めたが、番号がOCR誤読）
  if (nameIsOk && hasCrossCheckMismatch && primaryMatch) {
    return (
      <div className="space-y-0.5 text-[10px]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <span className="text-green-600">
            {nameLabel}マスタ一致: <span className="font-medium">{primaryMatch.master_value}</span>
          </span>
          <span className="text-gray-500">
            正しいコード: <span className="font-mono font-bold text-blue-700">{primaryMatch.master_code}</span>
          </span>
          <span className="inline-flex items-center px-1 py-0.5 rounded bg-red-50 text-red-600 font-bold">
            {codeLabel}不一致
          </span>
        </div>
      </div>
    );
  }

  // パターン2: コードOK + 名前不一致（番号は正しいが、名前をOCR誤読）
  if (codeIsOk && codeMatch && !nameIsOk && primaryMatch) {
    return (
      <div className="space-y-0.5 text-[10px]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <span className="text-green-600">
            {codeLabel}マスタ一致: <span className="font-mono font-medium">{codeMatch.master_code}</span>
          </span>
          <span className="text-gray-500">
            正しい{nameLabel}: <span className="font-bold text-amber-700">{codeMatch.master_value}</span>
          </span>
          <span className="inline-flex items-center px-1 py-0.5 rounded bg-red-50 text-red-600 font-bold">
            {nameLabel}不一致
          </span>
        </div>
        {/* 名前の候補リスト */}
        {primaryMatch.candidates.length > 0 && (
          <div className="text-gray-400">
            候補: {primaryMatch.candidates.slice(0, 5).map((c, i) => (
              <span key={i} className="mr-1.5">
                <span className="text-gray-600">{c.name}</span>
                <span className="font-mono text-gray-400"> [{c.code}]</span>
                <span className="text-gray-400"> {Math.round(c.score)}%</span>
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  // パターン3: 両方不一致 or マスター照合がng/needs_review
  if (primaryMatch) {
    return (
      <div className="space-y-0.5 text-[10px]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          {primaryMatch.master_value && (
            <span className="text-gray-500">
              マスタ: <span className="font-medium text-amber-700">{primaryMatch.master_value}</span>
            </span>
          )}
          {primaryMatch.master_code && (
            <span className="text-gray-500">
              コード: <span className="font-mono font-medium text-amber-700">{primaryMatch.master_code}</span>
            </span>
          )}
          {primaryMatch.match_score > 0 && primaryMatch.match_status !== 'ok' && (
            <span className="text-amber-600">
              一致率: {Math.round(primaryMatch.match_score)}%
            </span>
          )}
          {hasCrossCheckMismatch && (
            <span className="inline-flex items-center px-1 py-0.5 rounded bg-red-50 text-red-600 font-bold">
              コード不一致
            </span>
          )}
        </div>
        {/* 候補リスト（番号逆引きと名前マッチで改行分割） */}
        {primaryMatch.candidates.length > 0 && (() => {
          const codeCandidates = primaryMatch.candidates.filter(c => c.name.includes('（番号'));
          const nameCandidates = primaryMatch.candidates.filter(c => !c.name.includes('（番号'));
          return (
            <div className="text-[10px] space-y-0.5">
              {codeCandidates.length > 0 && (
                <div className="text-gray-500">
                  番号から: {codeCandidates.slice(0, 2).map((c, i) => (
                    <span key={i} className="mr-1.5">
                      <span className="font-medium text-blue-700">{c.name}</span>
                      <span className="font-mono text-gray-400"> [{c.code}]</span>
                    </span>
                  ))}
                </div>
              )}
              {nameCandidates.length > 0 && (
                <div className="text-gray-400">
                  候補: {nameCandidates.slice(0, 5).map((c, i) => (
                    <span key={i} className="mr-1.5">
                      <span className="text-gray-600">{c.name}</span>
                      <span className="font-mono text-gray-400"> [{c.code}]</span>
                      <span className="text-gray-400"> {Math.round(c.score)}%</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })()}
      </div>
    );
  }

  return null;
}

/**
 * 金融機関グループ表示コンポーネント
 * 「銀行名・銀行番号」または「支店名・店番号」をセットで表示し、
 * マスター照合情報はグループの下に1回だけ表示する
 */
function FinancialFieldGroup({
  nameField,
  codeField,
  nameLabel,
  codeLabel,
  allFields,
}: {
  nameField: OcrField | undefined;
  codeField: OcrField | undefined;
  nameLabel: string;
  codeLabel: string;
  allFields: OcrField[];
}) {
  const nameValue = nameField?.corrected_value || nameField?.value || '-';
  const codeValue = codeField?.corrected_value || codeField?.value || '-';

  // マスター情報: 名前フィールドのmaster_matchを優先（銀行名/支店名に照合情報がある）
  const primaryMatch = nameField?.master_match;
  const codeMatch = codeField?.master_match;

  // グループ全体の状態を判定（問題がある場合に背景色を付ける）
  const hasIssue = primaryMatch?.cross_check_status === 'mismatch'
    || codeMatch?.cross_check_status === 'mismatch'
    || primaryMatch?.match_status === 'ng'
    || primaryMatch?.match_status === 'needs_review'
    || codeMatch?.match_status === 'ng'
    || codeMatch?.match_status === 'needs_review';

  const hasValidMatch = primaryMatch && primaryMatch.match_status !== 'unverified';

  return (
    <div className={`border-b border-gray-200 ${hasIssue ? 'bg-amber-50/30' : ''}`}>
      {/* 名前行 */}
      <div className="flex items-center text-xs py-2.5 px-0 gap-2">
        <span className="w-28 text-gray-500 flex-shrink-0">{nameLabel}</span>
        <span className="flex-shrink-0">
          {nameField ? <InlineCheckBadge field={nameField} allFields={allFields} /> : (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-400">-</span>
          )}
        </span>
        <span className="flex-1 text-gray-800 font-semibold text-right">{nameValue}</span>
      </div>
      {/* コード行 */}
      <div className="flex items-center text-xs py-2.5 px-0 gap-2">
        <span className="w-28 text-gray-500 flex-shrink-0">{codeLabel}</span>
        <span className="flex-shrink-0">
          {codeField ? <InlineCheckBadge field={codeField} allFields={allFields} /> : (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-400">-</span>
          )}
        </span>
        <span className="flex-1 text-gray-800 font-semibold text-right">{codeValue}</span>
      </div>
      {/* マスター照合情報（グループ下に1回だけ表示 - 3パターン対応） */}
      {hasIssue && (
        <div className="pl-2 pb-2 ml-28">
          <FinancialGroupMatchDetail
            primaryMatch={primaryMatch}
            codeMatch={codeMatch}
            nameLabel={nameLabel}
            codeLabel={codeLabel}
          />
        </div>
      )}
      {/* 問題なし（OK）の場合もマスター情報を表示 */}
      {!hasIssue && hasValidMatch && primaryMatch && (
        <div className="pl-2 pb-2 ml-28">
          <MasterMatchDetail masterMatch={primaryMatch} />
        </div>
      )}
    </div>
  );
}

/**
 * バッチファイル詳細コンポーネント
 * 右側パネル:
 *   - 原本PDFプレビュー + OCR抽出結果（チェック結果バッジ付き）を左右並列表示
 *   - 処理ログタブ
 */
export default function BatchFileDetail({
  file,
  batchId,
  onReprocess,
}: BatchFileDetailProps) {
  const [activeTab, setActiveTab] = useState<TabId>('preview_ocr');
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
    { id: 'preview_ocr', label: '原本PDFプレビュー / OCR抽出結果', icon: '📄' },
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

  // OCR主要項目フィールド名リスト（銀行名/番号・支店名/番号はグループ表示のため除外）
  const mainFields = [
    '預金者氏名',
    '預金者フリガナ',
    'お届出印金融機関',
    '__bank_group__',   // 銀行名・銀行番号グループ
    '__branch_group__', // 支店名・店番号グループ
    '預金種目',
    '口座番号',
    'ゆうちょ記号',
    'ゆうちょ番号',
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
      <div className="flex-1 overflow-y-auto">
        {/* 原本PDFプレビュー + OCR抽出結果（チェック結果バッジ統合） */}
        {activeTab === 'preview_ocr' && (
          <div className="grid grid-cols-1 xl:grid-cols-2 h-full min-h-[500px]">
            {/* 左側: PDFプレビュー */}
            <div className="border-r border-gray-200 h-full min-h-[500px]">
              {file.status === 'completed' || file.status === 'needs_review' ? (
                <iframe
                  key={`${file.file_id}-${file.status}`}
                  src={`/api/result/${file.file_id}/pdf-preview`}
                  className="w-full h-full min-h-[500px]"
                  title="PDFプレビュー"
                />
              ) : file.status === 'processing' ? (
                <div className="flex flex-col items-center justify-center h-full gap-3">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
                  <span className="text-sm text-gray-400">OCR処理中...</span>
                </div>
              ) : file.status === 'failed' ? (
                <div className="flex items-center justify-center h-full text-red-400 text-sm">
                  処理に失敗しました
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                  処理待ちです
                </div>
              )}
            </div>

            {/* 右側: OCR抽出結果 + チェックバッジ統合 */}
            <div className="p-4 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
                </div>
              ) : document ? (
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <h4 className="text-xs font-semibold text-gray-600">OCR抽出結果（主要項目）</h4>
                  </div>
                  <div className="space-y-0">
                    {mainFields.map((fieldName) => {
                      // 銀行名・銀行番号グループ
                      if (fieldName === '__bank_group__') {
                        const bankNameField = document.fields.find((f) => f.field_name === '銀行名');
                        const bankCodeField = document.fields.find((f) => f.field_name === '銀行番号');
                        return (
                          <FinancialFieldGroup
                            key="bank_group"
                            nameField={bankNameField}
                            codeField={bankCodeField}
                            nameLabel="銀行名"
                            codeLabel="銀行番号"
                            allFields={document.fields}
                          />
                        );
                      }
                      // 支店名・店番号グループ
                      if (fieldName === '__branch_group__') {
                        const branchNameField = document.fields.find((f) => f.field_name === '支店名');
                        const branchCodeField = document.fields.find((f) => f.field_name === '店番号');
                        return (
                          <FinancialFieldGroup
                            key="branch_group"
                            nameField={branchNameField}
                            codeField={branchCodeField}
                            nameLabel="支店名"
                            codeLabel="店番号"
                            allFields={document.fields}
                          />
                        );
                      }
                      // 通常フィールド
                      const field = document.fields.find((f) => f.field_name === fieldName);
                      const value = field?.corrected_value || field?.value || '-';
                      return (
                        <div key={fieldName}>
                          <div className="flex items-center text-xs border-b border-gray-100 py-2.5 gap-2">
                            {/* フィールド名 */}
                            <span className="w-28 text-gray-500 flex-shrink-0">{fieldName}</span>
                            {/* チェック結果バッジ */}
                            <span className="flex-shrink-0">
                              {field ? <InlineCheckBadge field={field} allFields={document.fields} /> : (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-400">
                                  -
                                </span>
                              )}
                            </span>
                            {/* 値 */}
                            <span className="flex-1 text-gray-800 font-semibold text-right">{value}</span>
                          </div>
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
          </div>
        )}

        {/* 処理ログタブ */}
        {activeTab === 'log' && (
          <div className="p-4">
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
