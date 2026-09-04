// ヘルスチェック用エンドポイント
//
// Dockerのhealthcheckが叩く軽量な生存確認用ルート。
// 認証ミドルウェアの対象外とし（middleware.tsのPUBLIC_PATHSに追加）、
// 常に200を返すことで、未認証状態でもコンテナがhealthyと判定されるようにする。

import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export function GET() {
  return NextResponse.json({ status: 'ok' });
}
