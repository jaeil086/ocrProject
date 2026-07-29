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

/** OCR認識フィールド */
export interface OcrField {
  field_name: string;
  value: string | null;
  confidence_score: number;
  confidence_level: ConfidenceLevel;
  is_confirmed: boolean;
  corrected_value: string | null;
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
  corrected_value: string;
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
