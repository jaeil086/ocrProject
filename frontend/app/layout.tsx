import type { Metadata } from "next";
import "./globals.css";

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
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-white shadow-sm border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <h1 className="text-xl font-bold text-gray-800">
              OCR口座振替依頼書処理システム
            </h1>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
