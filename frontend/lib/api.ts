// APIクライアント - OCR口座振替依頼書処理システム

import type {
  UploadResponse,
  OcrDocument,
  OcrField,
  VisualCheck,
  BatchUploadResponse,
  BatchStatusResponse,
} from '@/types';

const API_BASE = '/api';

// ============================================================
// 認証（BFF方式）
// ============================================================

/** ログイン中ユーザー情報 */
export interface SessionUser {
  email: string | null;
  username: string | null;
  groups: string[];
  is_admin: boolean;
}

/**
 * 認証付きfetchラッパー
 * - httpOnly Cookie を送信するため credentials: 'include' を常に付与する。
 * - 401（未認証/期限切れ）を受けたらログイン画面へ遷移する。
 */
async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, { ...init, credentials: 'include' });
  if (res.status === 401) {
    // セッション切れ: ログイン開始エンドポイントへ遷移
    if (typeof window !== 'undefined') {
      window.location.href = '/api/auth/login';
    }
    throw new Error('認証セッションが切れました。ログイン画面に移動します。');
  }
  return res;
}

/**
 * ログイン中ユーザー情報を取得する
 * 未認証の場合は null を返す。
 */
export async function getSession(): Promise<SessionUser | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (res.status === 401) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/**
 * ログアウトする
 * バックエンドでCookieを破棄し、Cognitoのログアウトへ遷移する。
 */
export async function logout(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await res.json().catch(() => ({}));
    window.location.href = data.logout_url || '/';
  } catch {
    window.location.href = '/';
  }
}

/**
 * PDFファイルアップロード + 自動OCR処理
 * 複数ファイル対応
 */
export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));

  // 2段階OCR処理のため長めのタイムアウト（5分）
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300000);

  try {
    const res = await authFetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    if (!res.ok) throw new Error(await res.text());
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * OCR処理結果取得
 */
export async function getResult(fileId: string): Promise<OcrDocument> {
  const res = await authFetch(`${API_BASE}/result/${fileId}`);

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * フィールド修正（corrected_value設定, is_confirmed=True）
 */
export async function updateField(
  fileId: string,
  fieldName: string,
  correctedValue: string
): Promise<OcrField> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/fields`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field_name: fieldName, corrected_value: correctedValue }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * フィールドチェックステータス変更（手動でOK/NG/確認必要を設定）
 */
export async function updateFieldCheckStatus(
  fileId: string,
  fieldName: string,
  checkStatus: 'ok' | 'ng' | 'needs_review'
): Promise<OcrField> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/fields`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field_name: fieldName, check_status: checkStatus }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * 目視確認ステータス更新
 */
export async function updateVisualCheck(
  fileId: string,
  checkItem: string,
  isChecked: boolean,
  checkedBy: string
): Promise<VisualCheck> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/visual-checks`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      check_item: checkItem,
      is_checked: isChecked,
      checked_by: checkedBy,
    }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * 確認完了処理
 */
export async function confirmDocument(
  fileId: string,
  confirmedBy: string
): Promise<OcrDocument> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed_by: confirmedBy }),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * CSVダウンロード
 * Shift_JISエンコードされたCSVファイルをダウンロード
 */
export async function downloadCsv(fileId: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/csv`);

  if (!res.ok) throw new Error(await res.text());

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  // Content-Dispositionヘッダーからファイル名を取得
  a.download =
    res.headers.get('content-disposition')?.split("''")[1] || `${fileId}.csv`;
  a.click();
  window.URL.revokeObjectURL(url);
}

/**
 * リネーム済みPDFダウンロード
 */
export async function downloadPdf(fileId: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/result/${fileId}/pdf`);

  if (!res.ok) throw new Error(await res.text());

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  // Content-Dispositionヘッダーからファイル名を取得
  a.download =
    res.headers.get('content-disposition')?.split("''")[1] || `${fileId}.pdf`;
  a.click();
  window.URL.revokeObjectURL(url);
}

// === バッチ処理API ===

/**
 * バッチアップロード（複数PDF一括アップロード）
 * バックグラウンドでOCR処理を開始し、batch_idを返す
 */
export async function batchUpload(files: File[]): Promise<BatchUploadResponse> {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));

  const res = await authFetch(`${API_BASE}/batch/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * バッチ処理状況取得（ポーリング用）
 */
export async function getBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  const res = await authFetch(`${API_BASE}/batch/${batchId}/status`);

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * 個別ファイル再処理
 */
export async function reprocessFile(
  batchId: string,
  fileId: string
): Promise<{ message: string; file_id: string; batch_id: string }> {
  const res = await authFetch(`${API_BASE}/batch/${batchId}/files/${fileId}/reprocess`, {
    method: 'POST',
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * バッチ全体結果Excelダウンロード（チェック項目色分け付き）
 */
export async function downloadBatchCsv(batchId: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/batch/${batchId}/download/csv`);

  if (!res.ok) throw new Error(await res.text());

  const contentType = res.headers.get('content-type') || '';

  // S3 pre-signed URLが返された場合
  if (contentType.includes('application/json')) {
    const data = await res.json();
    const a = document.createElement('a');
    a.href = data.download_url;
    a.download = data.filename || `OCR_BATCH_RESULT_${batchId}.xlsx`;
    a.click();
    return;
  }

  // フォールバック: 直接バイナリが返された場合
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download =
    res.headers.get('content-disposition')?.split("''")[1] ||
    `OCR_BATCH_RESULT_${batchId}.xlsx`;
  a.click();
  window.URL.revokeObjectURL(url);
}

/**
 * バッチ全原本PDFのZIPダウンロード
 */
export async function downloadBatchZip(batchId: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/batch/${batchId}/download/zip`);

  if (!res.ok) throw new Error(await res.text());

  const contentType = res.headers.get('content-type') || '';

  // S3 pre-signed URLが返された場合
  if (contentType.includes('application/json')) {
    const data = await res.json();
    const a = document.createElement('a');
    a.href = data.download_url;
    a.download = data.filename || `OCR_BATCH_RESULT_${batchId}.zip`;
    a.click();
    return;
  }

  // フォールバック: 直接バイナリが返された場合
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download =
    res.headers.get('content-disposition')?.split("''")[1] ||
    `OCR_BATCH_RESULT_${batchId}.zip`;
  a.click();
  window.URL.revokeObjectURL(url);
}

// ============================================================
// 監査ログ閲覧（管理者限定）
// ============================================================

/** 監査ログ1件 */
export interface AuditLogEntry {
  timestamp: string;
  event_type: string;
  result: string;
  user_email: string | null;
  user_groups: string[];
  target_file: string | null;
  ip_address: string | null;
  user_agent: string | null;
  detail: string | null;
}

/** 監査ログ検索レスポンス */
export interface AuditLogResponse {
  logs: AuditLogEntry[];
  total: number;
  offset: number;
  limit: number;
}

/** 監査ログ検索フィルタ */
export interface AuditLogFilter {
  dateFrom?: string;     // YYYY-MM-DD
  dateTo?: string;       // YYYY-MM-DD
  eventType?: string;
  userEmail?: string;
  keyword?: string;
  offset?: number;
  limit?: number;
}

/**
 * 監査ログを検索して取得する（管理者限定）
 * 管理者以外は 403 になる。
 */
export async function getAuditLogs(
  filter: AuditLogFilter = {}
): Promise<AuditLogResponse> {
  const params = new URLSearchParams();
  if (filter.dateFrom) params.set('date_from', filter.dateFrom);
  if (filter.dateTo) params.set('date_to', filter.dateTo);
  if (filter.eventType) params.set('event_type', filter.eventType);
  if (filter.userEmail) params.set('user_email', filter.userEmail);
  if (filter.keyword) params.set('keyword', filter.keyword);
  params.set('offset', String(filter.offset ?? 0));
  params.set('limit', String(filter.limit ?? 100));

  const res = await authFetch(`${API_BASE}/audit/logs?${params.toString()}`);
  if (res.status === 403) {
    throw new Error('この画面を表示する権限がありません（管理者のみ）');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** イベント種別一覧を取得する（管理者限定） */
export async function getAuditEventTypes(): Promise<
  { value: string; label: string }[]
> {
  const res = await authFetch(`${API_BASE}/audit/event-types`);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.event_types ?? [];
}
