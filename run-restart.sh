#!/bin/bash

# AI News Bot - コンテナ再起動スクリプト
# コンテナを停止し、ビルドして再起動します

set -e  # エラーが発生したら停止

echo "========================================"
echo "AI News Bot コンテナ再起動"
echo "========================================"

# 環境選択
if [ "$1" = "dev" ]; then
    ENV="dev"
    COMPOSE_FILE="conf/docker-compose-dev.yml"
    CONTAINER_NAME="ai-newsbot-scheduler-dev"
elif [ "$1" = "prod" ] || [ -z "$1" ]; then
    ENV="prod"
    COMPOSE_FILE="conf/docker-compose-prod.yml"
    CONTAINER_NAME="ai-newsbot-scheduler-prod"
else
    echo "❌ 不明な環境: $1"
    echo "使用方法: ./run-restart.sh [dev|prod]"
    echo "  デフォルト: prod"
    exit 1
fi

echo "🎯 対象環境: $ENV"
echo "📄 使用ファイル: $COMPOSE_FILE"
echo ""

# Dockerの確認
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerが見つかりません"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Composeが見つかりません"
    exit 1
fi

# 既存コンテナの停止
echo "🛑 既存コンテナを停止中..."
docker compose -f $COMPOSE_FILE down

# コンテナのビルドと起動
echo ""
echo "🔨 コンテナをビルド中..."
docker compose -f $COMPOSE_FILE build

echo ""
echo "🚀 コンテナを起動中..."
docker compose -f $COMPOSE_FILE up -d

# トークンの確認（bindマウントされているのでコピー不要）
if [ -f app/credentials/token.pickle ]; then
    echo ""
    echo "✅ 認証トークンが検出されました（自動マウント）"
else
    echo ""
    echo "⚠️  認証トークンが見つかりません"
    echo "   初回セットアップを実行してください: ./run-install.sh"
fi

# ステータス確認
echo ""
echo "📊 コンテナステータス:"
docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "========================================"
echo "✅ 再起動が完了しました！"
echo "========================================"
echo ""
echo "📝 次のコマンド:"
echo "  ログ確認: docker logs -f $CONTAINER_NAME"
echo "  コンテナに入る: docker exec -it $CONTAINER_NAME sh"
echo "  停止: docker compose -f $COMPOSE_FILE down"
echo ""

# 最初の数行のログを表示
echo "📋 起動ログ (最初の10行):"
echo "----------------------------------------"
docker logs --tail 10 $CONTAINER_NAME 2>&1 || echo "⚠️  ログ取得中..."