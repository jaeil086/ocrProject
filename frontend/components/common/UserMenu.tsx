'use client';

// ログインユーザー表示 + ログアウトメニュー
//
// - マウント時に /api/auth/me からユーザー情報を取得し、メールアドレスを表示する。
// - ログアウトボタンでバックエンドのログアウト処理を呼び出し、Cognitoのログアウトへ遷移する。

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getSession, logout, type SessionUser } from '@/lib/api';

export default function UserMenu() {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getSession()
      .then((u) => {
        if (mounted) setUser(u);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <div className="text-xs text-gray-400">読み込み中...</div>;
  }

  if (!user || !user.email) {
    return null;
  }

  const roleLabel = user.is_admin ? '管理者' : '利用者';

  return (
    <div className="flex items-center gap-3">
      <div className="text-right leading-tight">
        <p className="text-sm font-medium text-gray-800">{user.email}</p>
        <p className="text-xs text-gray-400">{roleLabel}</p>
      </div>
      {user.is_admin && (
        <Link
          href="/admin/logs"
          className="text-xs text-blue-700 border border-blue-300 bg-blue-50 rounded px-3 py-1.5 hover:bg-blue-100 transition-colors duration-150"
        >
          監査ログ
        </Link>
      )}
      <button
        onClick={() => logout()}
        className="text-xs text-gray-600 border border-gray-300 rounded px-3 py-1.5 hover:bg-gray-50 transition-colors duration-150"
        aria-label="ログアウト"
      >
        ログアウト
      </button>
    </div>
  );
}
