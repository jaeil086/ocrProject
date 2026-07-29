/** @type {import('next').NextConfig} */
const nextConfig = {
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
};

module.exports = nextConfig;
