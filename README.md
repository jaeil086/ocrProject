# OCRシステム セットアップ・実行手順

## 概要

本システムは、預金口座振替届出書をOCR解析し、必要な情報を抽出してCSV形式で出力するシステムです。

---

# 技術構成

## Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS

## Backend

- FastAPI
- Python
- AWS Bedrock (Claude)
- Pandas
- PyMuPDF
- OpenCV

---

# 事前準備

以下のソフトウェアがインストールされていることを確認してください。

## Node.js

確認方法

```bash
node -v
npm -v
```

---

## Python

確認方法

```bash
python --version
```

推奨バージョン

```text
Python 3.11以上
```

---

# ソースコード取得

GitHubからプロジェクトを取得します。

```bash
git clone <Repository URL>
```

例

```bash
git clone https://github.com/xxxxx/ocr-project.git
```

プロジェクトディレクトリへ移動

```bash
cd ocr-project
```

---

# Frontendセットアップ

Frontendディレクトリへ移動

```bash
cd frontend
```

## パッケージインストール

```bash
npm install
```

※ 初回のみ実行

---

## Frontend起動

```bash
npm run dev
```

起動後、ブラウザで以下へアクセスしてください。

```text
http://localhost:3000
```

---

# Backendセットアップ

Backendディレクトリへ移動

```bash
cd backend
```

---

## 仮想環境作成

```bash
python -m venv .venv
```

※ 初回のみ実行

---

## 仮想環境有効化

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

正常に有効化されると以下のように表示されます。

```text
(.venv)
PS C:\...
```

---

## Pythonライブラリインストール

```bash
pip install -r requirements.txt
```

※ 初回のみ実行

このコマンドにより、プロジェクトで利用するライブラリが一括インストールされます。

主なライブラリ

- FastAPI
- Uvicorn
- Boto3
- Pandas
- PyMuPDF
- OpenCV
- python-dotenv

---

# 環境変数設定

Backendディレクトリに `.env` ファイルを配置してください。

例

```env
AWS_PROFILE=default
AWS_REGION=ap-northeast-1

BEDROCK_MODEL_ID=anthropic.claude-sonnet-4.6
```

※ 実際の値は利用環境に合わせて設定してください。

---

# AWS認証

AWS SSOを利用する場合

```bash
aws sso login --profile <profile-name>
```

例

```bash
aws sso login --profile cheiru
```

ログイン確認

```bash
aws sts get-caller-identity --profile cheiru
```

---

# Backend起動

Backendディレクトリで以下を実行します。

```bash
uvicorn app.main:app --reload
```

または

```bash
python -m uvicorn app.main:app --reload
```

起動後

```text
http://localhost:8000
```

でアクセス可能となります。

---

# システム起動手順

```text
Git Clone
    ↓
Frontend依存関係インストール
(npm install)
    ↓
Backend仮想環境作成
(python -m venv .venv)
    ↓
仮想環境有効化
    ↓
Pythonライブラリインストール
(pip install -r requirements.txt)
    ↓
AWS SSOログイン
    ↓
Backend起動
    ↓
Frontend起動
    ↓
OCR実行
```

---

# よくあるエラー

## npm コマンドが見つからない

原因

```text
Node.jsがインストールされていない
```

確認

```bash
node -v
npm -v
```

---

## uvicorn が見つからない

原因

```text
仮想環境が有効になっていない
または
requirements.txtがインストールされていない
```

対応

```bash
pip install -r requirements.txt
```

---

## No module named xxxx

原因

```text
必要なライブラリがインストールされていない
```

対応

```bash
pip install -r requirements.txt
```

---

## AWS認証エラー

原因

```text
AWS SSOの認証期限切れ
```

対応

```bash
aws sso login --profile <profile-name>
```

再ログインを実施してください。


---

# ディレクトリ構成例

```text
ocr-project
│
├─ frontend
│   ├─ src
│   ├─ public
│   └─ package.json
│
├─ backend
│   ├─ app
│   ├─ .venv
│   ├─ requirements.txt
│   └─ .env
│
└─ README.md
```