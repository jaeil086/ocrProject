// OCR口座振替依頼書処理システム - TypeScript型定義

/** 帳票様式区分 */
export type FormType = 'yucho' | 'general';

/** 書類ステータス */
export type DocumentStatus =
  | 'uploading'
  | 'processing'
  | 'normal'
  | 'deficient'
  | 'needs_review';

/** Confidence Score判定レベル */
export type ConfidenceLevel = 'high' | 'low';

/** バリデーションエラー種別 */
export type ValidationErrorType =
  | '記入漏れ'
  | '銀行番号不一致'
  | '店番号不一致'
  | '銀行番号不存在'
  | '店番号不存在';

/** 目視確認種別 */
export type VisualCheckType = '目視確認必要' | '確認者チェック必要';

/** マスターマッチング候補 */
export interface MasterMatchCandidate {
  name: string;
  code: string;
  score: number;
}

/** 金融機関マスターとのマッチング結果 */
export interface MasterMatchInfo {
  master_value: string | null;
  master_code: string | null;
  match_score: number;
  match_status: 'ok' | 'needs_review' | 'ng' | 'unverified';
  candidates: MasterMatchCandidate[];
  cross_check_status: 'ok' | 'mismatch' | null;
}

/** OCR認識フィールド */
export interface OcrField {
  field_name: string;
  value: string | null;
  confidence_score: number;
  confidence_level: ConfidenceLevel;
  is_confirmed: boolean;
  corrected_value: string | null;
  master_match: MasterMatchInfo | null;
  manual_check_status: 'ok' | 'ng' | 'needs_review' | null;
}

/** バリデーションエラー */
export interface ValidationError {
  field_name: string;
  error_type: ValidationErrorType;
  message: string;
}

/** 目視確認項目 */
export interface VisualCheck {
  check_item: string;
  check_type: VisualCheckType;
  is_checked: boolean;
  checked_by: string | null;
  checked_at: string | null;
}

/** OCR処理ドキュメント（メインモデル） */
export interface OcrDocument {
  file_id: string;
  original_filename: string;
  form_type: FormType | null;
  status: DocumentStatus;
  fields: OcrField[];
  validation_errors: ValidationError[];
  visual_checks: VisualCheck[];
  consignor_number: string | null;
  contract_number: string | null;
  bank_name: string | null;
  branch_name: string | null;
  bank_code: string | null;
  branch_code: string | null;
  account_number: string | null;
  depositor_name: string | null;
  created_at: string;
  updated_at: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
}

/** アップロードレスポンス */
export interface UploadResponse {
  files: Array<{
    file_id: string;
    original_filename: string;
    status: DocumentStatus;
    fields: OcrField[];
    errors: ValidationError[];
  }>;
  total_count: number;
}

/** フィールド修正リクエスト */
export interface FieldUpdateRequest {
  field_name: string;
  corrected_value?: string;
  check_status?: 'ok' | 'ng' | 'needs_review' | null;
}

/** 目視確認更新リクエスト */
export interface VisualCheckUpdateRequest {
  check_item: string;
  is_checked: boolean;
  checked_by: string;
}

/** 確認完了リクエスト */
export interface ConfirmRequest {
  confirmed_by: string;
}

// === バッチ処理関連の型定義 ===

/** バッチファイルステータス */
export type BatchFileStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'needs_review'
  | 'failed';

/** バッチジョブ全体ステータス */
export type BatchJobStatus =
  | 'uploading'
  | 'processing'
  | 'completed'
  | 'partial';

/** バッチ処理ログエントリ */
export interface BatchLogEntry {
  timestamp: string;
  message: string;
  level: string;
}

/** バッチ処理ファイル項目 */
export interface BatchFileItem {
  file_id: string;
  seq_number: number;
  original_filename: string;
  batch_filename: string;
  consignor_number: string | null;
  contract_number: string | null;
  status: BatchFileStatus;
  progress: number;
  error_message: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  updated_at: string;
  logs: BatchLogEntry[];
}

/** バッチ処理状況レスポンス */
export interface BatchStatusResponse {
  batch_id: string;
  status: BatchJobStatus;
  total_files: number;
  completed: number;
  processing: number;
  needs_review: number;
  failed: number;
  queued: number;
  progress_percent: number;
  created_at: string;
  updated_at: string;
  files: BatchFileItem[];
}

/** バッチアップロードレスポンス */
export interface BatchUploadResponse {
  batch_id: string;
  total_files: number;
  message: string;
  files: BatchFileItem[];
}
