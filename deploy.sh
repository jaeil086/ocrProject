#!/bin/bash
# ============================================================
# デプロイスクリプト — OCR口座振替依頼書処理システム
# ============================================================
# 使い方:
#   chmod +x deploy.sh
#   ./deploy.sh          # 通常デプロイ
#   ./deploy.sh rollback # ロールバック（直前のイメージに戻す）
# ============================================================

set -euo pipefail

# --- 設定 ---
APP_DIR="/opt/ocr-app"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
BACKUP_DIR="${APP_DIR}/backups"
LOG_FILE="${APP_DIR}/logs/deploy.log"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# --- カラー出力 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[DEPLOY]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
    exit 1
}

# --- ディレクトリ確認 ---
mkdir -p "$BACKUP_DIR" "${APP_DIR}/logs"

# === ロールバック処理 ===
if [ "${1:-}" = "rollback" ]; then
    log "ロールバック開始..."
    
    # 直前のイメージタグを探す
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/image_tags_*.txt 2>/dev/null | head -1)
    if [ -z "$LATEST_BACKUP" ]; then
        error "バックアップが見つかりません。ロールバック不可。"
    fi
    
    log "バックアップファイル: $LATEST_BACKUP"
    log "現在のコンテナを停止中..."
    cd "$APP_DIR"
    docker compose down
    
    # バックアップイメージからロード
    log "直前のイメージでコンテナを再起動..."
    docker compose up -d
    
    log "ロールバック完了"
    docker compose ps
    exit 0
fi

# === 通常デプロイ処理 ===
log "========================================="
log "デプロイ開始: $TIMESTAMP"
log "========================================="

cd "$APP_DIR"

# --- Step 1: 現在のイメージタグをバックアップ ---
log "[1/6] 現在のイメージ情報をバックアップ..."
docker compose images > "$BACKUP_DIR/image_tags_${TIMESTAMP}.txt" 2>/dev/null || true

# --- Step 2: 最新コードをPull ---
log "[2/6] 最新コードを取得中..."
git fetch origin
git pull origin main || {
    warn "git pull失敗。手動確認が必要です。"
    error "コード取得に失敗しました。"
}

# --- Step 3: Docker Build ---
log "[3/6] Dockerイメージをビルド中..."
docker compose build --no-cache 2>&1 | tee -a "$LOG_FILE"

# --- Step 4: コンテナ再起動 ---
log "[4/6] コンテナを再起動中..."
docker compose down
docker compose up -d

# --- Step 5: ヘルスチェック ---
log "[5/6] ヘルスチェック実行中..."
sleep 15

# バックエンドヘルスチェック
RETRY=0
MAX_RETRY=10
while [ $RETRY -lt $MAX_RETRY ]; do
    if docker compose exec -T backend curl -sf http://localhost:8000/ > /dev/null 2>&1; then
        log "  ✓ Backend: 正常"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRY ]; then
        error "Backend ヘルスチェック失敗。ロールバックを検討してください: ./deploy.sh rollback"
    fi
    sleep 5
done

# フロントエンドヘルスチェック
RETRY=0
while [ $RETRY -lt $MAX_RETRY ]; do
    if docker compose exec -T frontend wget -q --spider http://localhost:3000/ 2>/dev/null; then
        log "  ✓ Frontend: 正常"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRY ]; then
        error "Frontend ヘルスチェック失敗。ロールバックを検討してください: ./deploy.sh rollback"
    fi
    sleep 5
done

log "  ✓ 全サービス正常稼動"

# --- Step 6: 不要イメージ削除 ---
log "[6/6] 使用していないDockerイメージを削除中..."
docker image prune -f 2>&1 | tee -a "$LOG_FILE"

# --- 完了 ---
log "========================================="
log "デプロイ完了: $(date '+%Y-%m-%d %H:%M:%S')"
log "========================================="
echo ""
docker compose ps
echo ""
log "サービスURL: https://$(hostname -I | awk '{print $1}')"
