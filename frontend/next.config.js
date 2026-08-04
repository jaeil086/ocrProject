/** @type {import('next').NextConfig} */
const nextConfig = {
  // 開発時のuseEffect二重実行を抑制
  reactStrictMode: false,
  // バックエンドAPIプロキシ設定
  // /api/* へのリクエストをFastAPIバックエンド(localhost:8000)に転送
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
  // 2段階OCR処理に対応するためタイムアウトを延長
  experimental: {
    proxyTimeout: 300000, // 5分
  },
};

module.exports = nextConfig;
