// Next.js Middleware — 未認証アクセスのガード（BFF方式）
//
// 役割:
//   - 保護対象ページへのアクセス時に、認証セッション（httpOnly Cookie）の有無を確認する。
//   - セッションが無い場合はバックエンドのログイン開始エンドポイント（/api/auth/login）へ
//     リダイレクトし、Cognito Hosted UIのログイン画面へ誘導する。
//
// 補足:
//   - トークンの厳密な検証（署名・有効期限）はバックエンドのJWT検証で行う。
//     ここではCookie有無による軽量なゲートに留め、UXとして未認証を早期にログインへ回す。
//   - IDトークンCookie名はバックエンドの auth.py と一致させる（ocr_id_token）。

import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// バックエンドが発行するIDトークンCookie名
const ID_TOKEN_COOKIE = 'ocr_id_token';

// 認証不要でアクセスを許可するパス（プレフィックス一致）
const PUBLIC_PATHS = [
  '/api/auth', // ログイン・コールバック・ログアウト・me
];

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return true;
  // Next.jsの内部アセット・favicon等は除外（config.matcherでも除外しているが二重で安全に）
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/public') ||
    pathname === '/favicon.ico' ||
    pathname === '/logo-kiraboshi.png' ||
    pathname === '/bg-pattern.png'
  ) {
    return true;
  }
  return false;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(ID_TOKEN_COOKIE);
  if (hasSession) {
    return NextResponse.next();
  }

  // 未認証: バックエンドのログイン開始エンドポイントへリダイレクト
  // nextUrlを複製してパスだけ差し替えることで、リクエスト元のオリジン（Nginxのドメイン）を維持する。
  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/api/auth/login';
  loginUrl.search = '';
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // 静的アセット・画像・Next.js内部を除く全ページに適用
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.png$).*)'],
};
