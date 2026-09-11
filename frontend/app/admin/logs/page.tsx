'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  getSession,
  getAuditLogs,
  getAuditEventTypes,
  type AuditLogEntry,
  type SessionUser,
} from '@/lib/api';

const PAGE_SIZE = 100;

// イベント種別の日本語ラベル
const EVENT_LABELS: Record<string, string> = {
  login_success: 'ログイン成功',
  login_failure: 'ログイン失敗',
  logout: 'ログアウト',
  file_upload: 'ファイルアップロード',
  ocr_execute: 'OCR実行',
  result_download: '結果ダウンロード',
};

function eventLabel(v: string): string {
  return EVENT_LABELS[v] ?? v;
}

// UTC ISO文字列を日本時間の見やすい形式に変換
function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function AuditLogsPage() {
  // 認証状態
  const [session, setSession] = useState<SessionUser | null | undefined>(undefined);

  // フィルタ
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [eventType, setEventType] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [keyword, setKeyword] = useState('');

  // 結果
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [eventTypes, setEventTypes] = useState<{ value: string; label: string }[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // セッション確認
  useEffect(() => {
    getSession().then(setSession);
  }, []);

  // イベント種別一覧の取得（管理者のみ成功）
  useEffect(() => {
    if (session?.is_admin) {
      getAuditEventTypes()
        .then(setEventTypes)
        .catch(() => setEventTypes([]));
    }
  }, [session]);

  const fetchLogs = useCallback(
    async (nextOffset: number) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getAuditLogs({
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          eventType: eventType || undefined,
          userEmail: userEmail || undefined,
          keyword: keyword || undefined,
          offset: nextOffset,
          limit: PAGE_SIZE,
        });
        setLogs(res.logs);
        setTotal(res.total);
        setOffset(res.offset);
      } catch (e) {
        setError(e instanceof Error ? e.message : '取得に失敗しました');
        setLogs([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [dateFrom, dateTo, eventType, userEmail, keyword]
  );

  // 管理者確認後に初回ロード
  useEffect(() => {
    if (session?.is_admin) {
      fetchLogs(0);
    }
    // fetchLogs は依存が変わると再生成されるが、初回のみ実行したいので session に限定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  const handleSearch = () => {
    fetchLogs(0);
  };

  const handleReset = () => {
    setDateFrom('');
    setDateTo('');
    setEventType('');
    setUserEmail('');
    setKeyword('');
    // 状態更新後の値でfetchするため、次tickで実行
    setTimeout(() => {
      getAuditLogs({ offset: 0, limit: PAGE_SIZE })
        .then((res) => {
          setLogs(res.logs);
          setTotal(res.total);
          setOffset(0);
        })
        .catch((e) =>
          setError(e instanceof Error ? e.message : '取得に失敗しました')
        );
    }, 0);
  };

  // === 認証状態別の表示 ===

  if (session === undefined) {
    return (
      <div className="p-8 text-gray-500">読み込み中...</div>
    );
  }

  if (session === null) {
    return (
      <div className="p-8">
        <p className="text-gray-700">ログインが必要です。</p>
        <a href="/api/auth/login" className="text-blue-600 underline">
          ログイン画面へ
        </a>
      </div>
    );
  }

  if (!session.is_admin) {
    return (
      <div className="p-8">
        <h1 className="text-xl font-bold text-gray-800 mb-2">監査ログ</h1>
        <p className="text-red-600 mb-3">
          この画面は管理者のみ閲覧できます。
        </p>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← 処理画面へ戻る
        </Link>
      </div>
    );
  }

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <Link
        href="/"
        className="text-sm text-blue-600 hover:underline inline-block mb-3"
      >
        ← 処理画面へ戻る
      </Link>
      <h1 className="text-2xl font-bold text-gray-800 mb-1">監査ログ</h1>
      <p className="text-sm text-gray-500 mb-4">
        ログイン・アップロード・OCR実行などの操作履歴（新しい順）
      </p>

      {/* フィルタ */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-600 mb-1">開始日</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">終了日</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">イベント種別</label>
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
            >
              <option value="">すべて</option>
              {eventTypes.map((et) => (
                <option key={et.value} value={et.value}>
                  {eventLabel(et.value)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">
              ユーザーメール（部分一致）
            </label>
            <input
              type="text"
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
              placeholder="例: user@example.com"
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-gray-600 mb-1">
              キーワード（IP・ファイル名・詳細など）
            </label>
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="例: 123.253 / sample.pdf"
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-3">
          <button
            onClick={handleSearch}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-1.5 rounded"
          >
            検索
          </button>
          <button
            onClick={handleReset}
            className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm px-4 py-1.5 rounded"
          >
            リセット
          </button>
        </div>
      </div>

      {/* エラー */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3 mb-4">
          {error}
        </div>
      )}

      {/* 件数・ページング */}
      <div className="flex items-center justify-between mb-2 text-sm text-gray-600">
        <span>
          該当 {total} 件（{currentPage} / {totalPages} ページ）
        </span>
        <div className="flex gap-2">
          <button
            disabled={offset === 0 || loading}
            onClick={() => fetchLogs(Math.max(0, offset - PAGE_SIZE))}
            className="px-3 py-1 border border-gray-300 rounded disabled:opacity-40"
          >
            前へ
          </button>
          <button
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => fetchLogs(offset + PAGE_SIZE)}
            className="px-3 py-1 border border-gray-300 rounded disabled:opacity-40"
          >
            次へ
          </button>
        </div>
      </div>

      {/* テーブル */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-600 border-b border-gray-200">
              <th className="px-3 py-2 whitespace-nowrap">日時（JST）</th>
              <th className="px-3 py-2 whitespace-nowrap">イベント</th>
              <th className="px-3 py-2 whitespace-nowrap">結果</th>
              <th className="px-3 py-2 whitespace-nowrap">ユーザー</th>
              <th className="px-3 py-2 whitespace-nowrap">対象ファイル</th>
              <th className="px-3 py-2 whitespace-nowrap">IPアドレス</th>
              <th className="px-3 py-2 whitespace-nowrap">詳細</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                  読み込み中...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                  該当するログがありません
                </td>
              </tr>
            ) : (
              logs.map((log, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-100 hover:bg-gray-50 align-top"
                >
                  <td className="px-3 py-2 whitespace-nowrap">
                    {formatTimestamp(log.timestamp)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {eventLabel(log.event_type)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span
                      className={
                        log.result === 'failure'
                          ? 'text-red-600 font-medium'
                          : 'text-green-700'
                      }
                    >
                      {log.result === 'failure' ? '失敗' : '成功'}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {log.user_email || (
                      <span className="text-gray-400">（不明）</span>
                    )}
                  </td>
                  <td className="px-3 py-2 break-all">
                    {log.target_file || <span className="text-gray-400">-</span>}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {log.ip_address || <span className="text-gray-400">-</span>}
                  </td>
                  <td className="px-3 py-2 break-all text-gray-600">
                    {log.detail || <span className="text-gray-400">-</span>}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
