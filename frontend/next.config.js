/** @type {import('next').NextConfig} */
const nextConfig = {
  // 開発時のuseEffect二重実行を抑制 : Prevent multiple execution of useEffect
  reactStrictMode: false,
  // Docker standalone ビルド有効化（本番用軽量出力）
  output: "standalone",
  // バックエンドAPIプロキシ設定
  // /api/* へのリクエストをFastAPIバックエンドに転送する。
  // - Docker本番: 通常はNginxが /api/ を直接backendへプロキシするため、この経路は使われない。
  //   ただしNext.jsサーバー自身が /api/* を受けた場合の保険として backend:8000 を指す。
  // - 開発: localhost:8000。
  // 注意: rewrites の destination はサーバー側（Node）で評価されるため、
  //       NEXT_PUBLIC_ ではなくサーバー専用の API_PROXY_TARGET を使う（ビルド時埋め込みを避ける）。
  async rewrites() {
    const target =
      process.env.API_PROXY_TARGET ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
  // 2段階OCR処理に対応するためタイムアウトを延長
  experimental: {
    proxyTimeout: 300000, // 5分
  },
};

module.exports = nextConfig;
