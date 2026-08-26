/** @type {import('next').NextConfig} */
const nextConfig = {
  // 開発時のuseEffect二重実行を抑制 : Prevent multiple execution of useEffect
  reactStrictMode: false,
  // Docker standalone ビルド有効化（本番用軽量出力）
  output: "standalone",
  // バックエンドAPIプロキシ設定
  // /api/* へのリクエストをFastAPIバックエンド(localhost:8000)に転送
  // Docker環境ではNginxがプロキシするため、開発時のみ使用
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
  // 2段階OCR処理に対応するためタイムアウトを延長
  experimental: {
    proxyTimeout: 300000, // 5分
  },
};

module.exports = nextConfig;
