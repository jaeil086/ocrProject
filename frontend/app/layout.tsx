import type { Metadata } from "next";
import "./globals.css";
import UserMenu from "@/components/common/UserMenu";

export const metadata: Metadata = {
  title: "OCR口座振替依頼書処理システム",
  description: "口座振替依頼書PDFのOCR処理・データ検証・CSV出力を行うWebアプリケーション",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-gray-50 text-gray-900 flex flex-col">
        {/* ヘッダー */}
        <header className="bg-white shadow-sm border-b-4 border-blue-600">
          <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* きらぼし銀行ロゴ */}
              <a href="/">
                <img src="/logo-kiraboshi.png" alt="きらぼし銀行" height="36" className="h-9 cursor-pointer" />
              </a>
              <div className="border-l border-gray-300 pl-4">
                <p className="text-sm font-semibold text-gray-800">OCR口座振替依頼書処理システム</p>
                <p className="text-xs text-gray-500">AIによる口座振替依頼書の自動データ抽出</p>
              </div>
            </div>

            {/* ログインユーザー表示 + ログアウト */}
            <UserMenu />
          </div>
        </header>

        {/* メインコンテンツ */}
        <main className="flex-1">{children}</main>

        {/* フッター */}
        <footer className="bg-white border-t border-gray-200 py-4">
          <p className="text-center text-xs text-gray-400">
            &copy; Kiraboshi Bank, Ltd. All Rights Reserved.
          </p>
        </footer>
      </body>
    </html>
  );
}
