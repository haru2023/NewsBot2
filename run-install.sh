#!/bin/bash

# AI News Bot - 初回セットアップスクリプト
# このスクリプトは初回インストール時に必要な設定を行います

set -e  # エラーが発生したら停止

echo "========================================"
echo "AI News Bot セットアップを開始します"
echo "========================================"

# 1. 環境変数ファイルのセットアップ
echo ""
echo "📝 環境変数の設定..."
if [ ! -f conf/.env ]; then
    if [ -f conf/.env.example ]; then
        cp conf/.env.example conf/.env
        echo "✅ conf/.env.example から conf/.env を作成しました"
        echo "⚠️  conf/.env ファイルを編集して必要な値を設定してください:"
        echo "   - TEAMS_WEBHOOK_URL: Microsoft Teams Webhook URL"
        echo "   - X関連の認証情報（必要な場合）"
    else
        echo "❌ conf/.env.example が見つかりません"
        exit 1
    fi
else
    echo "✅ conf/.env ファイルは既に存在します"
fi

# 2. credentialsディレクトリの作成
echo ""
echo "📁 認証情報ディレクトリの作成..."
mkdir -p app/credentials
echo "✅ app/credentials ディレクトリを作成しました"

# 3. Gmail認証のセットアップ
echo ""
echo "🔐 Gmail認証のセットアップ..."
if [ ! -f app/credentials/credentials.json ]; then
    echo "❌ credentials.json が見つかりません"
    echo ""
    echo "📝 Gmail API認証情報の取得方法:"
    echo "1. https://console.cloud.google.com/ にアクセス"
    echo "2. プロジェクトを作成/選択"
    echo "3. 'APIs & Services' → 'Library' → 'Gmail API' を有効化"
    echo "4. 'APIs & Services' → 'Credentials' → 'Create Credentials' → 'OAuth client ID'"
    echo "5. Application type: 'Desktop app' を選択"
    echo "6. ダウンロードしたJSONファイルを app/credentials/credentials.json として保存"
    echo ""
    read -p "credentials.json を配置したら Enter キーを押してください..."

    if [ ! -f app/credentials/credentials.json ]; then
        echo "❌ credentials.json が配置されていません。セットアップを中止します。"
        exit 1
    fi
fi

echo "✅ credentials.json を検出しました"

# 4. Python依存関係のインストール
echo ""
echo "📦 Python依存関係のインストール..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt
    echo "✅ Python依存関係をインストールしました"
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt
    echo "✅ Python依存関係をインストールしました"
else
    echo "⚠️  pipが見つかりません。Dockerを使用する場合はスキップできます。"
fi

# 5. Gmail認証トークンの生成
echo ""
echo "🔑 Gmail認証トークンの生成..."
if [ ! -f app/credentials/token.pickle ]; then
    echo "初回認証を開始します..."
    python3 scripts/setup_gmail_auth.py

    if [ $? -eq 0 ] && [ -f app/credentials/token.pickle ]; then
        echo "✅ Gmail認証が完了しました"
    else
        echo "⚠️  Gmail認証がスキップされました。後で手動で実行してください:"
        echo "   python3 scripts/setup_gmail_auth.py"
    fi
else
    echo "✅ 既存のトークンを検出しました"
    echo "🔍 トークンの有効性を確認中..."

    # トークンの有効性チェックと自動更新
    if python3 scripts/setup_gmail_auth.py --check; then
        # チェック成功（有効またはリフレッシュ済み）
        echo "✅ Gmail認証の準備が完了しています"
    else
        # 再認証が必要
        echo "🔐 トークンの再認証を開始します..."
        python3 scripts/setup_gmail_auth.py

        if [ $? -eq 0 ] && [ -f app/credentials/token.pickle ]; then
            echo "✅ Gmail認証が更新されました"
        else
            echo "⚠️  Gmail認証の更新に失敗しました"
            echo "手動で実行してください: python3 scripts/setup_gmail_auth.py"
        fi
    fi
fi

# 6. Docker環境の確認
echo ""
echo "🐳 Docker環境の確認..."
if command -v docker &> /dev/null; then
    echo "✅ Dockerが検出されました"
    if docker compose version &> /dev/null; then
        echo "✅ Docker Composeが検出されました"
    else
        echo "❌ Docker Composeが見つかりません。Dockerの最新版をインストールしてください。"
        exit 1
    fi
else
    echo "❌ Dockerが見つかりません。Dockerをインストールしてください。"
    exit 1
fi

echo ""
echo "========================================"
echo "✅ セットアップが完了しました！"
echo "========================================"
echo ""
echo "📋 次のステップ:"
echo "1. conf/.env ファイルを編集して必要な環境変数を設定"
echo "2. コンテナの起動: ./run-restart.sh"
echo ""
echo "📝 定期実行スケジュール:"
echo "   - ニュース配信: 毎日 12:00"
echo "   - X投稿: 毎日 08:00"
echo ""
echo "🔧 トラブルシューティング:"
echo "   - Gmail認証の更新: python3 scripts/setup_gmail_auth.py"
echo "   - ログ確認: docker logs -f ai-newsbot-scheduler-prod"
echo "   - コンテナ再起動: ./run-restart.sh"