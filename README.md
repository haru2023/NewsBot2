# AI News Bot for Microsoft Teams

## 概要
社内SaaS開発チーム向けに、AI関連のニュースを自動収集してMicrosoft Teamsに投稿するBotです。
日本のテック系ニュースサイトから最新のAI技術トレンド、セキュリティ情報、開発ツールなどを厳選して配信します。

## 主な機能
- 📰 日本の主要テック系RSSフィードからAIニュースを自動収集
- 🔒 セキュリティ関連ニュースを優先的にフィルタリング
- 🤖 LLMを使用した関連性の高いニュースの選別（構造化JSON出力）
- 💬 Microsoft Teams Webhookへの自動投稿（Adaptive Cards形式）
- ⏰ Ofeliaスケジューラーによる1時間ごとの定期実行
- 🐳 Dockerコンテナでの簡単なデプロイ

## 対象ニュースカテゴリ（優先順位順）
1. **セキュリティ対応必須**: AIクラウドサービスやツールのセキュリティ・脆弱性情報
2. **新モデルリリース**: SLM/VLM/音声認識/OCRモデルのリリースや評判
3. **AI Coding Agent**: Cursor, Copilot, Continue, Windsurf等の更新
4. **AI Agent フレームワーク**: LangGraph, CrewAI, Dify, n8n等の新機能
5. **実用ツール**: Python/TypeScript/npmエコシステムのAI開発ツール

## セットアップ

### クイックスタート（初回セットアップ）
```bash
# 1. 初回セットアップを実行
./run-install.sh
# このスクリプトは以下を自動実行：
# - 環境変数ファイル作成 (conf/.env)
# - Python依存関係インストール
# - Gmail認証セットアップ
# - Docker環境確認

# 2. 環境変数を設定
vi conf/.env
# TEAMS_WEBHOOK_URL、X認証情報などを設定

# 3. コンテナ起動
./run-restart.sh        # 本番環境
./run-restart.sh dev    # 開発環境
```

### Docker環境（推奨）
```bash
# コンテナの起動・再起動
./run-restart.sh        # 本番環境
./run-restart.sh dev    # 開発環境

# 手動で即座に実行したい場合
docker exec ai-newsbot-scheduler-prod python /app/app/send_news.py   # ニュース配信
docker exec ai-newsbot-scheduler-prod python /app/app/send_tweet.py  # X投稿

# ログ確認
docker logs -f ai-newsbot-scheduler-prod

# コンテナに入る
docker exec -it ai-newsbot-scheduler-prod sh

# 停止
docker compose -f conf/docker-compose-prod.yml down
```

### Gmail認証の更新
```bash
# トークンの有効性確認と自動更新
python3 scripts/setup_gmail_auth.py --check

# 手動で再認証
python3 scripts/setup_gmail_auth.py
```

### ローカル実行（開発用）
```bash
# 依存関係インストール
pip3 install -r requirements.txt

# テストモード（Teams投稿なし）で実行
DRY_RUN=true python3 app/send_news.py

# 本番実行
python3 app/send_news.py
python3 app/send_tweet.py
```

## 設定内容

### 開発環境 (conf/docker-compose-dev.yml)
- **Teams Webhook**: テストチャネル用URL
- **LLM Endpoint**: `http://192.168.131.193:8008/v1/chat/completions`
- **MAX_NEWS_ITEMS**: 3件
- **DRY_RUN**: false (実際に投稿)
- **Scheduler**:
  - ニュース配信: 毎分実行（テスト用）
  - X投稿: 毎分実行（テスト用）

### 本番環境 (conf/docker-compose-prod.yml)
- **Teams Webhook**: 本番チャネル用URL
- **LLM Endpoint**: `http://192.168.131.193:8008/v1/chat/completions`
- **MAX_NEWS_ITEMS**: 5件
- **DRY_RUN**: false (実際に投稿)
- **Scheduler**:
  - ニュース配信: 毎日 12:00
  - X投稿: 毎日 08:00

## アーキテクチャ

```
NewsBot2/
├── run-install.sh              # 初回セットアップスクリプト
├── run-restart.sh              # コンテナ再起動スクリプト
├── requirements.txt            # Python依存関係
├── Dockerfile                  # Dockerイメージ定義
├── app/
│   ├── send_news.py           # ニュース配信スクリプト
│   ├── send_tweet.py          # X投稿スクリプト
│   ├── credentials/           # Gmail認証情報
│   │   ├── credentials.json   # OAuth認証情報
│   │   └── token.pickle       # 認証トークン
│   └── logs/                  # ログファイル
├── scripts/
│   └── setup_gmail_auth.py    # Gmail認証セットアップ
├── conf/
│   ├── .env.example           # 環境変数サンプル
│   ├── .env                   # 環境変数（要作成）
│   ├── docker-compose-dev.yml # 開発環境設定
│   └── docker-compose-prod.yml # 本番環境設定
└── doc/
    └── token-refresh-solution.md # Gmail認証ドキュメント
```

## 動作フロー

### ニュース配信（send_news.py）
1. **ニュース収集**: 日本の主要テック系サイトのRSSフィードから記事を収集
   - ITmedia AI+、GIGAZINE、Publickey、ZDNet Japan等
   - Developers.IO、Qiita、Zenn等の技術ブログも含む
2. **LLMフィルタリング**: OpenAI互換APIを使用して関連性の高い記事を選別
   - 法務・コンプライアンス関連を最優先
   - 構造化JSON出力で確実なパース
3. **スコアリング**: 各記事に関連性スコアとカテゴリを付与
4. **Teams投稿**: Adaptive Card形式でTeamsチャネルに投稿
   - タイムスタンプ付き（YYYY-MM-DD HH:MM形式）
   - カテゴリごとに色分け表示

### X投稿（send_tweet.py）
1. **Gmail認証**: OAuth2による認証（token.pickle使用）
2. **メール取得**: 過去30日間のX共有メールを取得
3. **フィルタリング**: 重複・既処理メールを除外
4. **投稿処理**: X APIを使用して投稿（未実装）

## トラブルシューティング

### Gmail認証エラー
```bash
# エラー: Token has been expired or revoked
# 解決方法：
python3 scripts/setup_gmail_auth.py
```

### Dockerコンテナが起動しない
```bash
# Docker Composeバージョン確認
docker compose version

# ログ確認
docker logs ai-newsbot-scheduler-prod
```

### LLMが応答しない
- LLM_ENDPOINTが正しく設定されているか確認
- ネットワーク接続を確認
- llama.cpp serverが起動しているか確認

### Teamsに投稿されない
- TEAMS_WEBHOOK_URLが正しいか確認
- DRY_RUNがfalseになっているか確認
- Webhookの有効期限を確認

### ニュースが少ない
- MAX_NEWS_ITEMSを増やす（現在は5件に設定）
- RSSフィードが正常に取得できているか確認
- LLMのフィルタリング基準を確認

## ニュースソース

### 日本語ソース
- ITmedia AI+ RSS
- ITmedia NEWS AI
- GIGAZINE
- ZDNet Japan AI
- CNET Japan
- Publickey
- はてなブックマーク テクノロジー

### 英語ソース
- Hacker News
- Hugging Face Blog

## ライセンス
MIT
