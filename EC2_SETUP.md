# EC2 サーバー構築ガイド — OCR口座振替依頼書処理システム

> **対象**: AWS初心者  
> **所要時間**: 約60〜90分  
> **前提**: AWSアカウントを保有していること

---

## 目次

1. [全体フロー概要](#1-全体フロー概要)
2. [EC2インスタンス作成](#2-ec2インスタンス作成)
3. [Key Pair（キーペア）作成](#3-key-pairキーペア作成)
4. [Security Group（セキュリティグループ）作成](#4-security-groupセキュリティグループ作成)
5. [Elastic IP（固定IP）の割り当て](#5-elastic-ip固定ipの割り当て)
6. [IAMロールの作成と付与](#6-iamロールの作成と付与)
7. [SSH接続](#7-ssh接続)
8. [Docker / Docker Compose インストール](#8-docker--docker-compose-インストール)
9. [アプリケーションデプロイ](#9-アプリケーションデプロイ)
10. [HTTPS（SSL証明書）の適用](#10-httpsssl証明書の適用)
11. [自動起動設定](#11-自動起動設定)
12. [Route53 / ドメイン設定（任意）](#12-route53--ドメイン設定任意)
13. [トラブルシューティング](#13-トラブルシューティング)

---

## 1. 全体フロー概要

```
AWS Console操作          EC2サーバー操作
─────────────────        ──────────────────
1. Key Pair作成
2. Security Group作成
3. EC2インスタンス作成
4. Elastic IP割り当て
5. IAMロール付与
                         6. SSH接続
                         7. Docker インストール
                         8. コードデプロイ
                         9. SSL証明書取得
                         10. サービス起動
```

---

## 2. EC2インスタンス作成

### 推奨スペック

| 項目 | 推奨値 | 理由 |
|------|--------|------|
| **OS** | Ubuntu 22.04 LTS (64bit, x86) | Docker公式サポート＋長期安定 |
| **インスタンスタイプ** | `t3.medium` (2vCPU / 4GB RAM) | OCR画像処理 + Next.js SSR に必要 |
| **EBSボリューム** | 30GB (gp3) | OS + Docker images + ログ + 一時ファイル |
| **リージョン** | ap-northeast-1 (東京) | Bedrockと同一リージョン |

> **コスト目安**: t3.medium = 約 $0.052/h ≒ 月額約 $38（24時間稼働時）

### 作成手順

1. [AWS Console](https://console.aws.amazon.com/) にログイン
2. リージョンが **アジアパシフィック（東京）ap-northeast-1** であることを確認（画面右上）
3. 検索バーに `EC2` と入力 → **EC2ダッシュボード** を開く
4. **「インスタンスを起動」** ボタンをクリック

#### 設定項目

| 設定 | 入力値 |
|------|--------|
| 名前 | `ocr-app-production` |
| AMI | Ubuntu Server 22.04 LTS (64-bit x86) |
| インスタンスタイプ | t3.medium |
| キーペア | 次のセクションで作成 |
| ネットワーク設定 | 次のセクションで作成するSGを選択 |
| ストレージ | 30 GiB gp3 |

5. 他の設定はデフォルトのまま → **「インスタンスを起動」**

---

## 3. Key Pair（キーペア）作成

EC2にSSH接続するための認証鍵です。

### 作成手順

1. EC2起動画面の「キーペア」セクションで **「新しいキーペアを作成」** をクリック
2. 以下を入力:

| 項目 | 値 |
|------|-----|
| キーペア名 | `ocr-app-key` |
| キーペアのタイプ | RSA |
| プライベートキーファイル形式 | `.pem` (Mac/Linux) / `.ppk` (Windows PuTTY) |

3. **「キーペアを作成」** → `.pem` ファイルが自動ダウンロードされる

### 重要な注意

- **このファイルは二度とダウンロードできません。** 安全な場所に保管してください。
- ファイルのパーミッションを制限する（後述のSSH接続時に必要）

---

## 4. Security Group（セキュリティグループ）作成

EC2へのネットワークアクセスを制御するファイアウォールです。

### 作成手順

1. EC2ダッシュボード → 左メニュー **「セキュリティグループ」** → **「セキュリティグループを作成」**
2. 基本情報:

| 項目 | 値 |
|------|-----|
| セキュリティグループ名 | `ocr-app-sg` |
| 説明 | `OCR application security group` |
| VPC | デフォルトVPC |

3. **インバウンドルール** (受信規則):

| タイプ | ポート | ソース | 用途 |
|--------|--------|--------|------|
| SSH | 22 | マイIP | SSH接続（自分のIPのみ許可） |
| HTTP | 80 | 0.0.0.0/0 | Web（HTTPS リダイレクト用） |
| HTTPS | 443 | 0.0.0.0/0 | Web（本番通信） |

4. **アウトバウンドルール** (送信規則):

| タイプ | ポート | 送信先 | 用途 |
|--------|--------|--------|------|
| すべてのトラフィック | すべて | 0.0.0.0/0 | 外部API（Bedrock/S3/Zengin）への通信 |

5. **「セキュリティグループを作成」** をクリック

### セキュリティのベストプラクティス

- SSH(22)のソースは **必ず「マイIP」** にする（全世界公開しない）
- オフィスや自宅のIPが変わった場合は、セキュリティグループを更新する
- 不要なポートは絶対に開けない

---

## 5. Elastic IP（固定IP）の割り当て

EC2インスタンスを再起動するとパブリックIPが変わります。Elastic IPを使えば固定IPを確保できます。

### 作成手順

1. EC2ダッシュボード → 左メニュー **「Elastic IP」** → **「Elastic IPアドレスの割り当て」**
2. リージョン: `ap-northeast-1` → **「割り当て」**
3. 割り当てられたIPを選択 → **「アクション」** → **「Elastic IPアドレスの関連付け」**
4. 対象インスタンスに `ocr-app-production` を選択 → **「関連付け」**

> **注意**: Elastic IPをインスタンスに紐づけないと課金対象になります。使わない場合は解放してください。

### Elastic IPの必要性

| 状況 | 必要性 |
|------|--------|
| ドメインを使う場合 | **必須**（DNSがIPを指すため） |
| IPアドレスで直接アクセス | **推奨**（再起動でIP変更を防ぐ） |
| テスト目的・一時利用 | 不要（パブリックIPで可） |

---

## 6. IAMロールの作成と付与

EC2からBedrock/S3にアクセスするためのIAM権限です。  
IAMロールを使えば、EC2内にAWSキーを保存する必要がありません（推奨方式）。

### IAMロール作成

1. AWS Console → **IAM** → **ロール** → **「ロールを作成」**
2. 信頼されたエンティティタイプ: **AWSのサービス**
3. ユースケース: **EC2** を選択 → **次へ**
4. ポリシーを追加:

| ポリシー名 | 用途 |
|-----------|------|
| `AmazonBedrockFullAccess` | OCRエンジン（Claude）呼び出し |
| `AmazonS3FullAccess` | PDF/Excel/ZIP保存 |

> **本番環境のベストプラクティス**: FullAccessの代わりにカスタムポリシーで最小権限を設定する。  
> 例: S3は特定バケット（`cheiru-ocr-storage`）のみ許可

5. ロール名: `ocr-app-ec2-role` → **「ロールを作成」**

### EC2にロールを付与

1. EC2ダッシュボード → 対象インスタンスを右クリック
2. **「セキュリティ」** → **「IAMロールを変更」**
3. `ocr-app-ec2-role` を選択 → **「IAMロールの更新」**

---

## 7. SSH接続

### Windows の場合

#### 方法1: PowerShell（Windows 10/11 標準）

```powershell
# .pemファイルのパーミッション設定
icacls "C:\Users\YourName\Downloads\ocr-app-key.pem" /inheritance:r /grant:r "%USERNAME%:R"

# SSH接続
ssh -i "C:\Users\YourName\Downloads\ocr-app-key.pem" ubuntu@<Elastic-IP>
```

#### 方法2: PuTTY

1. [PuTTY](https://www.putty.org/) をダウンロード・インストール
2. PuTTYgenで `.pem` → `.ppk` に変換:
   - PuTTYgen起動 → Load → `.pem`ファイル選択 → Save private key
3. PuTTYで接続:
   - Host Name: `ubuntu@<Elastic-IP>`
   - Port: 22
   - Connection → SSH → Auth → Private key: `.ppk`ファイルを指定
   - Open

### Mac / Linux の場合

```bash
# .pemファイルのパーミッション設定（初回のみ）
chmod 400 ~/Downloads/ocr-app-key.pem

# SSH接続
ssh -i ~/Downloads/ocr-app-key.pem ubuntu@<Elastic-IP>
```

### 接続確認

```bash
# 接続成功すると以下のようなプロンプトが表示される
ubuntu@ip-172-xx-xx-xx:~$

# OSバージョン確認
lsb_release -a
# → Ubuntu 22.04 LTS
```

---

## 8. Docker / Docker Compose インストール

SSH接続後、以下のコマンドを順番に実行します。

### Step 1: システム更新

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 2: Docker インストール

```bash
# 必要パッケージのインストール
sudo apt install -y ca-certificates curl gnupg lsb-release

# Docker公式GPGキー追加
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Dockerリポジトリ追加
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker Engine インストール
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# ubuntuユーザーをdockerグループに追加（sudoなしで実行可能に）
sudo usermod -aG docker ubuntu

# グループ変更を反映（再ログインまたは以下を実行）
newgrp docker
```

### Step 3: インストール確認

```bash
docker --version
# → Docker version 27.x.x

docker compose version
# → Docker Compose version v2.x.x

# テスト実行
docker run hello-world
```

---

## 9. アプリケーションデプロイ

### Step 1: ディレクトリ構造の作成

```bash
sudo mkdir -p /opt/ocr-app
sudo chown ubuntu:ubuntu /opt/ocr-app
cd /opt/ocr-app

# サブディレクトリ作成
mkdir -p logs uploads backups nginx/ssl
```

最終的なディレクトリ構造:

```
/opt/ocr-app/
├── backend/           # FastAPIソースコード
├── frontend/          # Next.jsソースコード
├── docker/            # Dockerfile群
├── nginx/
│   ├── nginx.conf     # Nginx設定
│   ├── nginx-http-only.conf  # HTTP-only設定（初期確認用）
│   └── ssl/           # SSL証明書
│       ├── fullchain.pem
│       └── privkey.pem
├── logs/              # アプリケーションログ
├── uploads/           # 一時アップロードファイル
├── backups/           # デプロイバックアップ
├── docker-compose.yml
├── deploy.sh
├── .env               # 環境変数（本番値）
└── .env.example       # 環境変数テンプレート
```

### Step 2: コードの配置

#### 方法A: Git clone（推奨）

```bash
cd /opt/ocr-app

# リポジトリをクローン（SSH or HTTPS）
git clone https://github.com/your-org/your-repo.git .

# または特定ブランチ
git clone -b main https://github.com/your-org/your-repo.git .
```

#### 方法B: SCP（ファイル転送）

ローカルPCからファイルを直接転送する場合:

```bash
# Windowsの場合（PowerShell）
scp -i "C:\Users\YourName\Downloads\ocr-app-key.pem" -r ./backend ./frontend ./docker ./nginx ./docker-compose.yml ubuntu@<Elastic-IP>:/opt/ocr-app/

# Mac/Linuxの場合
scp -i ~/Downloads/ocr-app-key.pem -r ./backend ./frontend ./docker ./nginx ./docker-compose.yml ubuntu@<Elastic-IP>:/opt/ocr-app/
```

### Step 3: 環境変数の設定

```bash
cd /opt/ocr-app

# テンプレートからコピー
cp .env.example .env

# 編集
nano .env
```

**最低限設定が必要な項目:**

```bash
# IAMロールを付与済みの場合、AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY は不要
# （コメントアウトまたは削除）

AWS_REGION=ap-northeast-1
BEDROCK_INFERENCE_PROFILE_ID=jp.anthropic.claude-sonnet-4-6
S3_BUCKET_NAME=cheiru-ocr-storage
ALLOWED_ORIGINS=https://your-domain.com
LOG_LEVEL=INFO
```

### Step 4: 初回起動（HTTP-onlyで動作確認）

SSL証明書取得前にまずHTTPで動作確認します。

```bash
cd /opt/ocr-app

# HTTP-only設定で起動
# docker-compose.yml の nginx volumes を一時変更:
#   ./nginx/nginx-http-only.conf:/etc/nginx/nginx.conf:ro
# かつ SSL volumeとポート443をコメントアウト

# ビルドと起動
docker compose build
docker compose up -d

# 状態確認
docker compose ps

# ログ確認
docker compose logs -f
```

ブラウザで `http://<Elastic-IP>` にアクセスしてフロントエンドが表示されれば成功です。

---

## 10. HTTPS（SSL証明書）の適用

### パターンA: ドメインを保有している場合（推奨）

Let's Encrypt + Certbot で無料SSL証明書を取得します。

#### 前提条件
- ドメインのDNS（AレコードまたはCNAME）がElastic IPを指していること

#### 手順

```bash
# Certbotインストール
sudo apt install -y certbot

# サービスを一時停止（80番ポートを開放するため）
cd /opt/ocr-app
docker compose down

# SSL証明書取得（standalone mode）
sudo certbot certonly --standalone \
  -d your-domain.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# 証明書が以下に生成される:
#   /etc/letsencrypt/live/your-domain.com/fullchain.pem
#   /etc/letsencrypt/live/your-domain.com/privkey.pem

# Nginx用にシンボリックリンク作成
sudo ln -sf /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/ocr-app/nginx/ssl/fullchain.pem
sudo ln -sf /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/ocr-app/nginx/ssl/privkey.pem

# パーミッション設定
sudo chmod 644 /opt/ocr-app/nginx/ssl/fullchain.pem
sudo chmod 640 /opt/ocr-app/nginx/ssl/privkey.pem
```

#### docker-compose.yml をHTTPS用に戻す

```bash
cd /opt/ocr-app

# nginx volumes を nginx.conf（HTTPS版）に変更:
#   ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
# SSL volumeとポート443を有効に

# サービス起動
docker compose up -d
```

#### 自動更新設定

Let's Encrypt証明書は90日で期限切れになるため、自動更新を設定:

```bash
# cronジョブ追加
sudo crontab -e

# 以下を追加（毎日午前3時に更新チェック）:
0 3 * * * certbot renew --quiet --deploy-hook "docker restart ocr-nginx"
```

---

### パターンB: ドメインなし（EC2 Public IPで運用）

ドメインを持っていない場合、Let's Encryptは使えません。以下の選択肢があります。

#### 方法1: 自己署名証明書（開発/社内利用向け）

```bash
cd /opt/ocr-app/nginx/ssl

# 自己署名証明書を生成（有効期限365日）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/C=JP/ST=Tokyo/L=Tokyo/O=OCR System/CN=localhost"

# サービス起動
cd /opt/ocr-app
docker compose up -d
```

> **注意**: ブラウザで「この接続は安全ではありません」警告が表示されます。社内利用で許容される場合のみ使用してください。

#### 方法2: HTTPのみで運用

SSL証明書なしでHTTPのみで運用する場合:

```bash
# docker-compose.yml の nginx volumes を以下に設定:
#   ./nginx/nginx-http-only.conf:/etc/nginx/nginx.conf:ro
# ポート443とSSL volumeは不要

docker compose up -d
```

> **注意**: HTTPは通信が暗号化されないため、インターネット経由で個人情報を扱う場合は非推奨です。

### 比較表

| 方式 | コスト | ブラウザ警告 | 適用範囲 |
|------|--------|-------------|---------|
| Let's Encrypt（ドメインあり） | 無料 | なし | **本番環境推奨** |
| 自己署名証明書 | 無料 | あり | 社内限定 |
| HTTPのみ | 無料 | なし | テスト/開発のみ |

---

## 11. 自動起動設定

EC2インスタンスが再起動した際に、自動でサービスが起動するよう設定します。

### 方法1: Docker restart policy（docker-compose.ymlに設定済み）

`docker-compose.yml` に `restart: unless-stopped` を設定済みのため、Dockerデーモンが起動すれば全コンテナが自動起動します。

Dockerデーモンの自動起動を確認:

```bash
# Docker がシステム起動時に自動起動するか確認
sudo systemctl is-enabled docker
# → enabled

# もし disabled の場合:
sudo systemctl enable docker
```

### 方法2: systemd サービス（より確実）

```bash
# systemdサービスファイル作成
sudo tee /etc/systemd/system/ocr-app.service > /dev/null << 'EOF'
[Unit]
Description=OCR Application (Docker Compose)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ocr-app
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

# サービス有効化
sudo systemctl daemon-reload
sudo systemctl enable ocr-app.service

# テスト
sudo systemctl start ocr-app.service
sudo systemctl status ocr-app.service
```

---

## 12. Route53 / ドメイン設定（任意）

### ドメインが必要な場合

| シナリオ | ドメインの必要性 |
|---------|----------------|
| 社内のみ利用（IP直接アクセス） | 不要 |
| 社外公開・HTTPS運用 | **必要**（Let's Encrypt利用のため） |
| わかりやすいURLが欲しい | 推奨 |

### Route53でドメインを設定する手順

1. **ドメイン購入**（既に持っている場合はスキップ）
   - AWS Console → Route53 → ドメインの登録
   - または外部レジストラ（お名前.com、Google Domains等）で購入

2. **ホストゾーン作成**
   - Route53 → ホストゾーン → 「ホストゾーンの作成」
   - ドメイン名: `your-domain.com`

3. **Aレコード追加**
   - レコード名: `ocr.your-domain.com`（サブドメイン）
   - レコードタイプ: A
   - 値: `<Elastic-IP>`
   - TTL: 300

4. **ネームサーバー設定**（外部レジストラの場合）
   - Route53のNSレコードに表示されている4つのネームサーバーを、ドメインレジストラの管理画面で設定

5. **DNS反映確認**

```bash
# DNS反映確認（数分〜最大48時間）
nslookup ocr.your-domain.com
# → Elastic IPが返ればOK
```

### Route53の費用

| 項目 | 費用 |
|------|------|
| ホストゾーン | $0.50/月 |
| DNSクエリ | $0.40/100万クエリ（ほぼ無料） |
| ドメイン購入 | 年額 $10〜$15（.com の場合） |

---

## 13. トラブルシューティング

### SSH接続できない

```bash
# 原因1: セキュリティグループのSSHルールにIPが許可されていない
# → AWSコンソールでSGのインバウンドルール確認

# 原因2: .pemファイルのパーミッションが広すぎる
chmod 400 ocr-app-key.pem   # Mac/Linux
# Windows: icacls でREAD権限のみに設定

# 原因3: ユーザー名が間違い
# Ubuntu AMIの場合: ubuntu
# Amazon Linux AMIの場合: ec2-user
```

### Docker build 失敗

```bash
# ディスク容量確認
df -h

# Docker キャッシュクリア
docker system prune -a --volumes

# メモリ不足の場合
free -h
# → t3.medium(4GB)で不足する場合はt3.largeへ変更検討
```

### コンテナが起動しない

```bash
# コンテナのステータス確認
docker compose ps

# ログ確認
docker compose logs backend
docker compose logs frontend
docker compose logs nginx

# 特定コンテナに入って確認
docker compose exec backend bash
docker compose exec frontend sh
```

### Backendが502 Bad Gatewayを返す

```bash
# Backendのヘルスチェック
curl http://localhost:8000/

# AWS認証確認（IAMロール）
docker compose exec backend python -c "import boto3; print(boto3.client('sts').get_caller_identity())"
```

### SSL証明書の更新が失敗

```bash
# 手動更新テスト
sudo certbot renew --dry-run

# ポート80がブロックされていないか確認
sudo lsof -i :80
```

---

## 付録: コスト見積もり（月額）

| サービス | 費用 |
|---------|------|
| EC2 (t3.medium, 24h稼働) | 約 $38 |
| EBS (30GB gp3) | 約 $2.4 |
| Elastic IP | 無料（インスタンスに紐づけ時） |
| S3 (10GB想定) | 約 $0.25 |
| Bedrock (Claude, 使用量次第) | 従量課金 |
| Route53 (任意) | 約 $0.50 |
| **合計（Bedrock除く）** | **約 $41/月** |

> Bedrockの費用はOCR処理量に依存します。Claude Sonnet 4の場合: 入力 $3/100万トークン、出力 $15/100万トークン（目安）

---

## チェックリスト

デプロイ完了時に確認すべき項目:

- [ ] EC2インスタンスが `running` 状態
- [ ] Elastic IPが割り当て済み
- [ ] Security Groupが正しく設定されている
- [ ] IAMロール（Bedrock + S3）が付与されている
- [ ] Docker / Docker Compose がインストール済み
- [ ] `.env` ファイルが正しく設定されている
- [ ] `docker compose up -d` で全コンテナが `healthy`
- [ ] `http://<IP>` でフロントエンドが表示される
- [ ] OCRアップロード → 結果表示が正常動作する
- [ ] SSL証明書が有効（ドメインありの場合）
- [ ] 自動起動が設定されている
