# Gmail Token更新の実装方針

## 問題点
Dockerコンテナ内で`run_local_server()`を使用した認証フローは以下の理由で機能しません：

1. **ポートアクセス不可**: コンテナ内のローカルサーバーにブラウザからアクセスできない
2. **ブラウザ起動不可**: ヘッドレス環境でブラウザを開けない
3. **リダイレクトURI問題**: localhost へのリダイレクトがコンテナ外から到達できない

## 解決策

### 推奨方法: ローカルで認証 → コンテナへコピー

```bash
# 1. ローカルで認証スクリプトを実行
cd /workspace/NewsBot2
python scripts/refresh_gmail_token.py

# 2. 生成されたトークンをコンテナにコピー
docker cp app/credentials/token.pickle ai-newsbot-scheduler-prod:/app/credentials/
```

### 実装: refresh_gmail_token.py

```python
#!/usr/bin/env python3
"""
Gmail認証トークンを更新するスクリプト
ローカル環境で実行し、生成されたtoken.pickleをコンテナにコピーする
"""

import pickle
import sys
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def refresh_token():
    """Gmail認証トークンを更新"""
    creds = None
    base_dir = Path(__file__).parent.parent
    token_path = base_dir / 'app/credentials/token.pickle'
    creds_path = base_dir / 'app/credentials/credentials.json'

    # credentials.jsonの存在確認
    if not creds_path.exists():
        print(f"❌ エラー: {creds_path} が見つかりません")
        print("Google Cloud Console から credentials.json をダウンロードしてください")
        return False

    # 既存トークンの読み込み試行
    if token_path.exists():
        print("📂 既存のトークンを読み込み中...")
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # トークンの検証とリフレッシュ
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 トークンをリフレッシュ中...")
            try:
                creds.refresh(Request())
                print("✅ トークンのリフレッシュに成功")
            except Exception as e:
                print(f"❌ リフレッシュ失敗: {e}")
                print("🔄 新規認証を開始します...")
                creds = None

        if not creds:
            print("🔐 ブラウザで認証を行ってください...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), SCOPES
            )
            creds = flow.run_local_server(
                port=0,
                success_message='認証成功！このタブを閉じてターミナルに戻ってください。'
            )

    # トークンの保存
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)
    print(f"💾 トークンを保存: {token_path}")

    # 接続テスト
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().labels().list(userId='me').execute()
        print(f"✅ Gmail API接続テスト成功（{len(results.get('labels', []))} ラベル取得）")
    except Exception as e:
        print(f"❌ Gmail API接続テスト失敗: {e}")
        return False

    # コンテナへのコピーコマンドを表示
    print("\n" + "="*60)
    print("📋 以下のコマンドでコンテナにトークンをコピーしてください:")
    print("="*60)
    print(f"docker cp {token_path} ai-newsbot-scheduler-prod:/app/credentials/")
    print("="*60)

    return True

if __name__ == "__main__":
    success = refresh_token()
    sys.exit(0 if success else 1)
```

### 代替案: サービスアカウント認証

OAuth2の代わりにサービスアカウントを使用（ドメイン全体の委任が必要）:

```python
from google.oauth2 import service_account

def authenticate_with_service_account():
    """サービスアカウントで認証（G Suite/Workspace環境のみ）"""
    credentials = service_account.Credentials.from_service_account_file(
        'path/to/service-account-key.json',
        scopes=SCOPES,
        subject='user@yourdomain.com'  # 委任するユーザー
    )
    service = build('gmail', 'v1', credentials=credentials)
    return service
```

### 自動化: GitHub Actions での定期更新

```yaml
name: Refresh Gmail Token

on:
  schedule:
    - cron: '0 0 1 * *'  # 毎月1日
  workflow_dispatch:

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

      - name: Refresh token
        env:
          CREDENTIALS_JSON: ${{ secrets.GMAIL_CREDENTIALS }}
          REFRESH_TOKEN: ${{ secrets.GMAIL_REFRESH_TOKEN }}
        run: |
          echo "$CREDENTIALS_JSON" > credentials.json
          python scripts/refresh_token_ci.py

      - name: Deploy to server
        run: |
          # SSHでトークンをサーバーにデプロイ
          scp token.pickle user@server:/path/to/app/credentials/
```

## エラー時の対処

### コンテナログでエラーを監視

```bash
# リアルタイムでログ監視
docker logs -f ai-newsbot-scheduler-prod 2>&1 | grep -E "(RefreshError|invalid_grant)"

# エラー時にSlack通知
docker logs ai-newsbot-scheduler-prod 2>&1 | \
  grep "invalid_grant" && \
  curl -X POST $SLACK_WEBHOOK -d '{"text":"⚠️ Gmail token expired!"}'
```

### send_tweet.py の改善案

```python
def authenticate(self):
    """Gmail API認証（改善版）"""
    token_path = Path(self.config.token_file)

    # ヘッドレス環境の検出
    is_headless = not os.environ.get('DISPLAY')

    if is_headless and not token_path.exists():
        logger.error("❌ ヘッドレス環境でtoken.pickleが見つかりません")
        logger.error("ローカル環境で以下を実行してください:")
        logger.error("1. python scripts/refresh_gmail_token.py")
        logger.error(f"2. docker cp app/credentials/token.pickle {os.environ.get('HOSTNAME', 'container')}:/app/credentials/")
        return False

    # 既存の認証フロー...
```

## まとめ

**推奨フロー**:
1. ローカル環境で `refresh_gmail_token.py` を実行
2. ブラウザで認証
3. 生成された `token.pickle` をコンテナにコピー
4. エラー監視とアラート設定

この方法により、コンテナ環境でも安定してGmail APIを利用できます。