#!/usr/bin/env python3
"""
Gmail認証のセットアップ/更新スクリプト
初回認証とトークン更新の両方に対応

使用方法:
1. このスクリプトをローカル環境で実行
2. ブラウザで認証
3. 生成されたtoken.pickleをコンテナにコピー
"""

import pickle
import sys
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def setup_gmail_auth():
    """Gmail認証をセットアップまたは更新"""
    creds = None
    base_dir = Path(__file__).parent.parent
    token_path = base_dir / 'app/credentials/token.pickle'
    creds_path = base_dir / 'app/credentials/credentials.json'

    print("="*60)
    print("Gmail認証セットアップツール")
    print("="*60)

    # credentials.jsonの存在確認
    if not creds_path.exists():
        print(f"❌ エラー: {creds_path} が見つかりません")
        print("\n📝 credentials.json の取得方法:")
        print("1. https://console.cloud.google.com/ にアクセス")
        print("2. プロジェクトを作成/選択")
        print("3. Gmail API を有効化")
        print("4. 認証情報 → OAuth 2.0 クライアントIDを作成")
        print("5. ダウンロードして app/credentials/credentials.json として保存")
        return False

    print(f"✅ credentials.json を検出: {creds_path}")

    # 既存トークンの確認
    if token_path.exists():
        print("📂 既存のトークンを検出、検証中...")
        with open(token_path, 'rb') as token:
            try:
                creds = pickle.load(token)
                print("✅ トークンの読み込み成功")
            except Exception as e:
                print(f"⚠️ トークンの読み込み失敗: {e}")
                creds = None
    else:
        print("🆕 初回セットアップを開始します")

    # トークンの検証と更新
    auth_needed = False
    if not creds:
        print("🔐 新規認証が必要です")
        auth_needed = True
    elif not creds.valid:
        if creds.expired and creds.refresh_token:
            print("🔄 トークンの有効期限切れ、リフレッシュを試行...")
            try:
                creds.refresh(Request())
                print("✅ トークンのリフレッシュ成功")
            except Exception as e:
                print(f"❌ リフレッシュ失敗: {e}")
                print("🔐 再認証が必要です")
                auth_needed = True
                creds = None
        else:
            print("🔐 トークンが無効、再認証が必要です")
            auth_needed = True
            creds = None
    else:
        print("✅ 既存のトークンは有効です")

    # 新規認証が必要な場合
    if auth_needed:
        print("\n" + "="*60)
        print("🌐 ブラウザで認証を行ってください")
        print("="*60)
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_path), SCOPES
        )
        creds = flow.run_local_server(
            port=0,
            success_message='認証成功！このタブを閉じてターミナルに戻ってください。'
        )
        print("✅ 認証完了")

    # トークンの保存
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)
    print(f"💾 トークンを保存: {token_path}")

    # 接続テスト
    print("\n🧪 Gmail API接続テスト中...")
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        print(f"✅ 接続成功！{len(labels)} 個のラベルを取得")

        # メール数の確認
        inbox = service.users().messages().list(userId='me', maxResults=1).execute()
        if inbox.get('messages'):
            print("✅ メールボックスへのアクセス確認")
    except Exception as e:
        print(f"❌ Gmail API接続テスト失敗: {e}")
        return False

    # Dockerコンテナへのデプロイ手順
    print("\n" + "="*60)
    print("📋 Dockerコンテナへのデプロイ手順")
    print("="*60)
    print("1. 開発環境の場合（docker-compose）:")
    print(f"   docker cp {token_path} ai-newsbot-scheduler-dev:/app/credentials/")
    print("\n2. 本番環境の場合:")
    print(f"   docker cp {token_path} ai-newsbot-scheduler-prod:/app/credentials/")
    print("\n3. 動作確認:")
    print("   docker exec ai-newsbot-scheduler-prod python /app/app/send_tweet.py")
    print("="*60)

    return True

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Gmail認証のセットアップ/検証')
    parser.add_argument('--check', action='store_true', help='トークンの有効性チェックのみ実行')
    args = parser.parse_args()

    try:
        if args.check:
            # 検証モード
            base_dir = Path(__file__).parent.parent
            token_path = base_dir / 'app/credentials/token.pickle'

            if not token_path.exists():
                print("❌ トークンが存在しません")
                sys.exit(1)

            with open(token_path, 'rb') as f:
                creds = pickle.load(f)

            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    print("🔄 トークンの有効期限切れ、自動リフレッシュ中...")
                    creds.refresh(Request())
                    with open(token_path, 'wb') as f:
                        pickle.dump(creds, f)
                    print("✅ トークンを自動更新しました")
                    sys.exit(0)
                else:
                    print("❌ トークンが無効です。再認証が必要です")
                    sys.exit(1)
            else:
                print("✅ トークンは有効です")
                sys.exit(0)
        else:
            # セットアップモード
            success = setup_gmail_auth()
            sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 認証がキャンセルされました")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        sys.exit(1)