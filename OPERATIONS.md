# 運用ガイド — OCR口座振替依頼書処理システム

> **対象**: サーバー運用担当者  
> **前提**: EC2_SETUP.md の手順でデプロイが完了していること

---

## 目次

1. [日常運用コマンド](#1-日常運用コマンド)
2. [ログ管理](#2-ログ管理)
3. [バックアップ](#3-バックアップ)
4. [監視（モニタリング）](#4-監視モニタリング)
5. [デプロイ（更新）手順](#5-デプロイ更新手順)
6. [スケーリング](#6-スケーリング)
7. [セキュリティ運用](#7-セキュリティ運用)
8. [障害対応](#8-障害対応)
9. [定期メンテナンス](#9-定期メンテナンス)

---

## 1. 日常運用コマンド

### サービス状態確認

```bash
cd /opt/ocr-app

# 全コンテナの状態確認
docker compose ps

# 期待される出力:
# NAME            STATUS          PORTS
# ocr-nginx       Up (healthy)    0.0.0.0:80->80, 0.0.0.0:443->443
# ocr-frontend    Up (healthy)    3000/tcp
# ocr-backend     Up (healthy)    8000/tcp
```

### サービスの起動 / 停止 / 再起動

```bash
# 起動
docker compose up -d

# 停止（データは保持）
docker compose down

# 再起動（全コンテナ）
docker compose restart

# 特定のサービスのみ再起動
docker compose restart backend
docker compose restart frontend
docker compose restart nginx
```

### ヘルスチェック

```bash
# Backend API
curl -s http://localhost:8000/ | jq .
# → {"status": "ok", "service": "OCR口座振替依頼書処理システム"}

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
# → 200

# Nginx（外部から）
curl -sk https://<domain-or-ip>/health
# → OK
```

### リソース使用状況

```bash
# コンテナごとのCPU/メモリ使用量
docker stats --no-stream

# ディスク使用量
df -h

# Dockerディスク使用量
docker system df
```

---

## 2. ログ管理

### ログの場所

| ログ種類 | 場所 | 内容 |
|---------|------|------|
| Backend アプリログ | Docker volume `app-logs` | OCR処理結果、エラー |
| Nginx アクセスログ | Docker volume `nginx-logs` | HTTPリクエスト |
| Nginx エラーログ | Docker volume `nginx-logs` | 接続エラー、502等 |
| Docker コンテナログ | `docker compose logs` | 全出力（stdout/stderr） |

### ログの確認

```bash
cd /opt/ocr-app

# リアルタイムログ（全サービス）
docker compose logs -f

# 特定サービスのログ
docker compose logs -f backend
docker compose logs -f nginx

# 直近100行のみ表示
docker compose logs --tail=100 backend

# 特定時間以降のログ
docker compose logs --since="2025-01-01T00:00:00" backend
```

### ログローテーション

Docker のデフォルトログドライバーでは、ログファイルが際限なく肥大化します。制限を設定:

```bash
# /etc/docker/daemon.json を作成/編集
sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
EOF

# Docker デーモン再起動
sudo systemctl restart docker

# コンテナ再起動（ログ設定反映）
cd /opt/ocr-app
docker compose down
docker compose up -d
```

### Nginxログのローテーション

Nginx volume内のログは手動ローテーション:

```bash
# cron設定
sudo tee /etc/cron.weekly/nginx-log-rotate > /dev/null << 'EOF'
#!/bin/bash
docker exec ocr-nginx sh -c 'mv /var/log/nginx/access.log /var/log/nginx/access.log.old && kill -USR1 1'
find /var/lib/docker/volumes/*nginx-logs*/_data -name "*.old" -mtime +30 -delete
EOF
sudo chmod +x /etc/cron.weekly/nginx-log-rotate
```

---

## 3. バックアップ

### バックアップ対象

| 対象 | 重要度 | 方法 |
|------|--------|------|
| `.env` | 最重要 | 手動コピー |
| `nginx/ssl/` | 重要 | 手動コピー（証明書） |
| `backend/data/zengin_cache/` | 中 | 自動再取得可能 |
| Docker volumes | 中 | 定期バックアップ |
| アプリケーションコード | 低 | Git管理で復元可能 |

> **注意**: OCR処理データはS3に保存されるため、EC2上のバックアップは最小限で可。

### 自動バックアップスクリプト

```bash
# /opt/ocr-app/scripts/backup.sh
sudo tee /opt/ocr-app/scripts/backup.sh > /dev/null << 'SCRIPT'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/ocr-app/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

# バックアップ作成
tar -czf "$BACKUP_FILE" \
  /opt/ocr-app/.env \
  /opt/ocr-app/nginx/ssl/ \
  /opt/ocr-app/docker-compose.yml \
  /opt/ocr-app/nginx/nginx.conf \
  2>/dev/null || true

# 古いバックアップを削除（30日以上前）
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +30 -delete

echo "[$(date)] バックアップ完了: $BACKUP_FILE"
SCRIPT

chmod +x /opt/ocr-app/scripts/backup.sh
```

### バックアップの自動実行（cron）

```bash
# 毎日午前2時にバックアップ
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/ocr-app/scripts/backup.sh >> /opt/ocr-app/logs/backup.log 2>&1") | crontab -
```

---

## 4. 監視（モニタリング）

### 基本的な死活監視スクリプト

```bash
# /opt/ocr-app/scripts/healthcheck.sh
sudo tee /opt/ocr-app/scripts/healthcheck.sh > /dev/null << 'SCRIPT'
#!/bin/bash
set -euo pipefail

LOG_FILE="/opt/ocr-app/logs/healthcheck.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

check_service() {
    local name=$1
    local url=$2
    local status

    status=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

    if [ "$status" = "200" ]; then
        echo "[$TIMESTAMP] OK: $name (HTTP $status)" >> "$LOG_FILE"
    else
        echo "[$TIMESTAMP] FAIL: $name (HTTP $status)" >> "$LOG_FILE"
        # 異常時にサービスを再起動
        echo "[$TIMESTAMP] $name 再起動を試行..." >> "$LOG_FILE"
        cd /opt/ocr-app && docker compose restart "$name" >> "$LOG_FILE" 2>&1
    fi
}

check_service "backend" "http://localhost:8000/"
check_service "frontend" "http://localhost:3000/"
SCRIPT

chmod +x /opt/ocr-app/scripts/healthcheck.sh

# 5分ごとにヘルスチェック実行
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/ocr-app/scripts/healthcheck.sh") | crontab -
```

### CloudWatch連携（推奨）

EC2のシステムメトリクスをCloudWatchで監視する設定:

```bash
# CloudWatch Agent インストール
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
rm amazon-cloudwatch-agent.deb

# 設定ファイル作成
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null << 'EOF'
{
  "metrics": {
    "namespace": "OCR-App",
    "metrics_collected": {
      "cpu": {
        "measurement": ["cpu_usage_idle", "cpu_usage_user", "cpu_usage_system"],
        "metrics_collection_interval": 60
      },
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": ["used_percent"],
        "resources": ["/"],
        "metrics_collection_interval": 60
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/opt/ocr-app/logs/deploy.log",
            "log_group_name": "/ocr-app/deploy",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/opt/ocr-app/logs/healthcheck.log",
            "log_group_name": "/ocr-app/healthcheck",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

# Agent 起動
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

# 自動起動有効化
sudo systemctl enable amazon-cloudwatch-agent
```

### CloudWatch アラーム設定（AWSコンソール）

以下のアラームの設定を推奨:

| メトリクス | 閾値 | アクション |
|-----------|------|-----------|
| CPU使用率 | > 80% (5分間) | SNS通知 |
| メモリ使用率 | > 85% | SNS通知 |
| ディスク使用率 | > 80% | SNS通知 |
| StatusCheckFailed | > 0 | インスタンス再起動 |

---

## 5. デプロイ（更新）手順

### 通常デプロイ

```bash
cd /opt/ocr-app

# デプロイスクリプト実行
chmod +x deploy.sh
./deploy.sh
```

### 手動デプロイ（スクリプトを使わない場合）

```bash
cd /opt/ocr-app

# 1. 最新コード取得
git pull origin main

# 2. イメージ再ビルド
docker compose build

# 3. コンテナ再起動
docker compose down
docker compose up -d

# 4. 動作確認
docker compose ps
curl http://localhost:8000/
```

### ロールバック

```bash
cd /opt/ocr-app
./deploy.sh rollback
```

### ゼロダウンタイムデプロイ（将来的な改善）

現在の構成ではコンテナ再起動時に短時間のダウンタイムが発生します。  
ゼロダウンタイムが必要な場合は以下を検討:
- Blue/Greenデプロイ（ELB + 2台構成）
- ローリングアップデート（Docker Swarm / ECS）

---

## 6. スケーリング

### 垂直スケーリング（インスタンスタイプ変更）

| 状況 | 推奨アクション |
|------|---------------|
| CPU使用率が常時80%超 | t3.medium → t3.large (8GB) |
| メモリ不足（OOM Kill） | t3.large → t3.xlarge (16GB) |
| 同時処理が頻繁 | workers数を増やす（docker-compose.yml） |

```bash
# Backend のworker数変更（docker-compose.yml を編集せずに）
docker compose exec backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### ディスク容量拡張

```bash
# 現在の使用量確認
df -h

# AWSコンソールでEBSボリュームサイズを変更後:
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1
```

---

## 7. セキュリティ運用

### 定期的に行うべきこと

| 頻度 | 作業 |
|------|------|
| 週次 | OSセキュリティアップデート |
| 月次 | Docker イメージ更新 |
| 月次 | SSH接続ログの確認 |
| 四半期 | IAMロール権限の見直し |
| 随時 | セキュリティグループのIP更新 |

### OSセキュリティアップデート

```bash
# セキュリティパッチのみ適用
sudo apt update
sudo apt upgrade -y --only-upgrade

# 自動セキュリティアップデート有効化
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### SSH接続ログ確認

```bash
# 最近のSSH接続（成功）
grep "Accepted" /var/log/auth.log | tail -20

# 不正アクセス試行（失敗）
grep "Failed" /var/log/auth.log | tail -20

# 不審なIPが多い場合はfail2banを導入
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 環境変数の保護

```bash
# .envファイルのパーミッション確認
ls -la /opt/ocr-app/.env
# → -rw------- 1 ubuntu ubuntu (本人のみ読み書き可)

# パーミッション設定
chmod 600 /opt/ocr-app/.env
```

---

## 8. 障害対応

### サービスが応答しない場合

```bash
# Step 1: コンテナ状態確認
docker compose ps

# Step 2: 問題のあるコンテナのログ確認
docker compose logs --tail=50 <service-name>

# Step 3: コンテナ再起動
docker compose restart <service-name>

# Step 4: それでもダメならイメージ再ビルド
docker compose down
docker compose build --no-cache <service-name>
docker compose up -d
```

### ディスクフル

```bash
# 原因特定
du -sh /var/lib/docker/*
du -sh /opt/ocr-app/logs/*

# Docker不要リソース削除
docker system prune -a --volumes

# 古いログ削除
find /opt/ocr-app/logs -name "*.log" -mtime +7 -delete
```

### メモリ不足（OOM）

```bash
# OOM Kill されたコンテナ確認
dmesg | grep -i "oom"
docker inspect <container-id> | grep -i "oomkilled"

# 対策:
# 1. 不要コンテナ停止
# 2. Backend workers数を減らす
# 3. インスタンスタイプ変更
```

### Backend が Bedrock に接続できない

```bash
# IAMロール確認
docker compose exec backend python -c "
import boto3
sts = boto3.client('sts')
print(sts.get_caller_identity())
"

# Bedrock接続テスト
docker compose exec backend python -c "
import boto3
client = boto3.client('bedrock-runtime', region_name='ap-northeast-1')
print('Bedrock接続OK')
"
```

---

## 9. 定期メンテナンス

### 月次メンテナンスチェックリスト

```markdown
- [ ] OSセキュリティアップデート実行
- [ ] Docker イメージ更新 (`docker compose pull`)
- [ ] ディスク使用率確認 (80%以下か)
- [ ] ログファイルサイズ確認
- [ ] バックアップの動作確認
- [ ] SSL証明書の有効期限確認
- [ ] セキュリティグループのレビュー
- [ ] CloudWatch アラーム動作確認
```

### SSL証明書期限確認

```bash
# 証明書の有効期限確認
sudo certbot certificates

# または
openssl x509 -in /opt/ocr-app/nginx/ssl/fullchain.pem -noout -dates
```

### Docker イメージ更新

```bash
cd /opt/ocr-app

# ベースイメージの更新を取得して再ビルド
docker compose build --pull --no-cache
docker compose down
docker compose up -d

# 古いイメージ削除
docker image prune -a -f
```

---

## 付録: よく使うコマンド一覧

| 操作 | コマンド |
|------|---------|
| 全サービス起動 | `docker compose up -d` |
| 全サービス停止 | `docker compose down` |
| ステータス確認 | `docker compose ps` |
| ログ確認（リアルタイム） | `docker compose logs -f` |
| Backend ログのみ | `docker compose logs -f backend` |
| コンテナ内に入る | `docker compose exec backend bash` |
| リソース使用状況 | `docker stats --no-stream` |
| ディスク確認 | `df -h` |
| デプロイ | `./deploy.sh` |
| ロールバック | `./deploy.sh rollback` |
| 不要リソース削除 | `docker system prune -a` |
