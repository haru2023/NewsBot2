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

### Docker実行

#### 開発環境での実行
```bash
# バックグラウンドで起動（1時間ごとに自動実行）
docker compose -f conf/docker-compose-dev.yml up -d

# ログ確認
docker logs -f ai-newsbot-dev

# 停止
docker compose -f conf/docker-compose-dev.yml down
```

#### 本番環境での実行
```bash
# バックグラウンドで起動（1時間ごとに自動実行）
docker compose -f conf/docker-compose-prod.yml up -d

# 手動で即座に実行したい場合
docker exec ai-newsbot-prod python send_news.py

# ログ確認
docker logs -f newsbot-scheduler-prod

# 停止
docker compose -f conf/docker-compose-prod.yml down
```

### ローカル実行（開発用）
```bash
# 依存関係インストール
pip install -r requirements.txt

# テストモード（Teams投稿なし）で実行
DRY_RUN=true python send_news.py

# 本番実行
python send_news.py
```

## 設定内容

### 開発環境 (conf/docker-compose-dev.yml)
- **Teams Webhook**: テストチャネル用URL
- **LLM Endpoint**: `http://192.168.131.193:8008/v1/chat/completions`
- **MAX_NEWS_ITEMS**: 3件
- **DRY_RUN**: false (実際に投稿)
- **Scheduler**: Ofelia - 起動から1時間後、以降1時間ごとに実行

### 本番環境 (conf/docker-compose-prod.yml)
- **Teams Webhook**: 本番チャネル用URL
- **LLM Endpoint**: `http://192.168.131.193:8008/v1/chat/completions`
- **MAX_NEWS_ITEMS**: 3件
- **DRY_RUN**: false (実際に投稿)
- **Scheduler**: Ofelia - 起動から1時間後、以降1時間ごとに実行

## アーキテクチャ

```
NewsBot/
├── send_news.py          # メインスクリプト
├── Dockerfile            # Dockerイメージ定義
├── requirements.txt      # Python依存関係
└── conf/
    ├── docker-compose-dev.yml   # 開発環境設定
    ├── docker-compose-prod.yml  # 本番環境設定
    └── ofelia.ini               # スケジューラー設定（未使用）
```

## 動作フロー

1. **ニュース収集**: 日本の主要テック系サイトのRSSフィードから記事を収集
   - ITmedia AI+、GIGAZINE、Publickey、ZDNet Japan等
   - Hacker News、Hugging Face Blogも含む
2. **LLMフィルタリング**: OpenAI互換APIを使用して関連性の高い記事を選別
   - セキュリティ関連ニュースを最優先
   - 構造化JSON出力で確実なパース
3. **スコアリング**: 各記事に関連性スコアとカテゴリを付与
4. **Teams投稿**: Adaptive Card形式でTeamsチャネルに投稿
   - タイムスタンプ付き（YYYY-MM-DD HH:MM形式）
   - カテゴリごとに色分け表示

## トラブルシューティング

### LLMが応答しない
- LLM_ENDPOINTが正しく設定されているか確認
- ネットワーク接続を確認
- llama.cpp serverが起動しているか確認

### Teamsに投稿されない
- TEAMS_WEBHOOK_URLが正しいか確認
- DRY_RUNがfalseになっているか確認
- Webhookの有効期限を確認

### ニュースが少ない
- MAX_NEWS_ITEMSを増やす（現在は3件に設定）
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
