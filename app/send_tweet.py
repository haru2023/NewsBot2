#!/usr/bin/env python3
"""
X (Twitter) Share via Gmail to Teams Bridge
AndroidのXアプリから共有したメールを処理してTeamsに投稿
"""

import os
import pytz
import requests
import re
import base64
import pickle
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

# Gmail API imports
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import setup_logger from util.log
from util.log import setup_logger

# Setup logging
logger = setup_logger(__name__)

# Gmail API スコープ
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'  # 既読マーク用
]

# Configuration
@dataclass
class Config:
    """Configuration settings"""
    teams_webhook_url: str = os.getenv("TEAMS_WEBHOOK_URL", "")

    # Gmail設定
    gmail_address: str = os.getenv("GMAIL_ADDRESS", "dummy@example.com")
    credentials_file: str = os.getenv("GMAIL_CREDENTIALS_FILE", "/workspace/NewsBot2/app/credentials/credentials.json")
    token_file: str = os.getenv("GMAIL_TOKEN_FILE", "/workspace/NewsBot2/app/credentials/token.pickle")

    # 処理設定
    check_hours_back: int = int(os.getenv("CHECK_HOURS_BACK_TWEET", "3"))  # X共有メール用：デフォルト3時間
    max_emails_per_run: int = int(os.getenv("MAX_EMAILS_PER_RUN", "5"))

    # フィルター設定
    process_only_unread: bool = os.getenv("PROCESS_ONLY_UNREAD", "true").lower() == "true"
    mark_as_read: bool = os.getenv("MARK_AS_READ", "true").lower() == "true"

    # LLM設定
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "http://192.168.131.193:8008/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"


class GmailClient:
    """Gmail API Client for fetching X share emails"""

    def __init__(self, config: Config):
        self.config = config
        self.service = None
        self.creds = None

    def authenticate(self):
        """Gmail API認証"""
        token_path = Path(self.config.token_file)
        creds_path = Path(self.config.credentials_file)

        # トークンが存在する場合は読み込み
        if token_path.exists():
            with open(token_path, 'rb') as token:
                self.creds = pickle.load(token)

        # 認証が無効または存在しない場合
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                logger.info("Refreshing Gmail token...")
                self.creds.refresh(Request())
            else:
                if not creds_path.exists():
                    logger.error(f"Credentials file not found: {creds_path}")
                    logger.info("Please download credentials.json from Google Cloud Console")
                    logger.info("1. Go to https://console.cloud.google.com/")
                    logger.info("2. Create/Select project → Enable Gmail API")
                    logger.info("3. Create credentials → OAuth 2.0 Client ID")
                    logger.info("4. Download and save as credentials.json")
                    return False

                logger.info("Authenticating with Gmail for the first time...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            # トークンを保存
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('gmail', 'v1', credentials=self.creds)
        # logger.info("Gmail authentication successful")  # 毎分は不要
        return True

    def search_x_share_emails(self) -> List[Dict]:
        """X共有メールを検索"""
        if not self.service:
            return []

        try:
            # 検索クエリ構築
            jst = pytz.timezone('Asia/Tokyo')
            after_date = datetime.now(jst) - timedelta(hours=self.config.check_hours_back)
            after_str = after_date.strftime("%Y/%m/%d")

            # 自分から自分へのメール、X/TwitterのURLを含む
            query_parts = [
                f"from:{self.config.gmail_address}",
                f"to:{self.config.gmail_address}",
                f"after:{after_str}",
                "(x.com OR twitter.com)"
            ]

            if self.config.process_only_unread:
                query_parts.append("is:unread")

            query = " ".join(query_parts)
            # logger.info(f"Gmail search query: {query}")  # 毎回出力は不要

            # メール検索（すべての対象メールを取得）
            all_messages = []
            page_token = None

            while True:
                results = self.service.users().messages().list(
                    userId='me',
                    q=query,
                    pageToken=page_token,
                    maxResults=100  # APIの1ページあたりの最大値
                ).execute()

                messages = results.get('messages', [])
                all_messages.extend(messages)

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            if all_messages:  # メールがある時だけログ出力
                logger.info(f"Found {len(all_messages)} X share emails total")

            # 各メールの詳細を取得（時間情報も含む）
            emails = []
            for msg in all_messages:
                email_data = self.get_email_details(msg['id'])
                if email_data:
                    emails.append(email_data)

            # 日付でソート（古い順）
            emails.sort(key=lambda x: x.get('internalDate', '0'))

            # 設定された上限数の-1, 0, +1をランダムに加算して処理対象とする
            max_count = self.config.max_emails_per_run # + random.randint(-1, 1)
            emails = emails[:max_count]

            if emails:
                logger.info(f"Processing {len(emails)} oldest emails")

            return emails

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return []

    def get_email_details(self, message_id: str) -> Optional[Dict]:
        """メールの詳細を取得"""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()

            # ヘッダーから情報取得
            headers = message['payload'].get('headers', [])
            subject = ""
            date = ""

            for header in headers:
                name = header['name']
                value = header['value']
                if name == 'Subject':
                    subject = value
                elif name == 'Date':
                    date = value

            # 本文を取得
            body = self.extract_body(message['payload'])

            return {
                'id': message_id,
                'subject': subject,
                'date': date,
                'body': body,
                'snippet': message.get('snippet', ''),
                'internalDate': message.get('internalDate', '0')  # ソート用のタイムスタンプ
            }

        except HttpError as e:
            logger.error(f"Error getting email details: {e}")
            return None

    def extract_body(self, payload) -> str:
        """メール本文を抽出"""
        body = ""

        # シングルパートメール
        if 'body' in payload and 'data' in payload['body']:
            data = payload['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

        # マルチパートメール
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body']['data']
                    body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif 'parts' in part:  # ネストされたパート
                    body += self.extract_body(part)

        return body

    def mark_as_read(self, message_id: str):
        """メールを既読にする"""
        if self.config.dry_run:
            logger.info(f"DRY RUN - Would mark email as read: {message_id}")
            return

        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked email as read: {message_id}")
        except HttpError as e:
            logger.error(f"Error marking email as read: {e}")


class XShareParser:
    """X共有メールの解析"""

    def extract_x_info(self, email: Dict) -> Optional[Dict]:
        """メールからX投稿情報を抽出"""

        body = email.get('body', '')
        subject = email.get('subject', '')

        # デバッグ：メール本文の最初の500文字をログ出力（必要時のみ有効化）
        # logger.debug(f"Email body preview: {body[:500]}...")
        # logger.debug(f"Email subject: {subject}")

        # X/TwitterのURLを抽出
        url_pattern = r'https?://(?:www\.)?(?:twitter\.com|x\.com)/(\w+)/status/(\d+)'
        url_match = re.search(url_pattern, body + ' ' + subject)

        if not url_match:
            logger.warning("No X/Twitter URL found in email")
            return None

        username = url_match.group(1)
        tweet_id = url_match.group(2)
        url = url_match.group(0)

        # 本文からツイートテキストを抽出（改善版）
        tweet_text = ""

        # 方法1: URLの前の部分から取得
        text_before_url = body.split(url)[0].strip()

        # 方法2: 全体から共有メールの定型文を除去
        full_text = body

        # Gmail共有の一般的なパターンを除去
        clean_patterns = [
            r'Check out.*?:\s*',
            r'Shared from.*?:\s*',
            r'From X.*?:\s*',
            r'.*shared.*tweet.*:\s*',
            r'---------- Forwarded message ---------.*?\n',
            r'From:.*?\n',
            r'Date:.*?\n',
            r'Subject:.*?\n',
            r'To:.*?\n'
        ]

        for pattern in clean_patterns:
            text_before_url = re.sub(pattern, '', text_before_url, flags=re.IGNORECASE | re.DOTALL)
            full_text = re.sub(pattern, '', full_text, flags=re.IGNORECASE | re.DOTALL)

        # URLとその後の余計な部分を削除
        full_text = re.sub(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/\S+.*', '', full_text, flags=re.DOTALL)
        # t.co短縮URLを削除
        full_text = re.sub(r'https?://t\.co/\S+', '', full_text)

        # 「ポストしました:」までの部分を削除
        if 'ポストしました:' in full_text:
            # 「ポストしました:」の後の部分のみを取得
            full_text = full_text.split('ポストしました:', 1)[-1]
            # 先頭の空白文字（改行、スペース、タブなど）を削除
            full_text = full_text.lstrip()

        # 改行で分割し、意味のあるテキストを探す
        lines = full_text.strip().split('\n')
        meaningful_lines = []

        for line in lines:
            line = line.strip()
            # 空行や短すぎる行をスキップ
            if line and len(line) > 3 and not line.startswith('--'):
                meaningful_lines.append(line)

        # 複数行のツイートに対応
        if meaningful_lines:
            tweet_text = '\n'.join(meaningful_lines[:10])  # 最大10行まで取得

        # ツイートテキストが取得できなかった場合のフォールバック
        if not tweet_text.strip():
            tweet_text = "[メール本文から抽出できませんでした]"
            logger.warning(f"Could not extract tweet text from email. Body length: {len(body)}")

        # logger.info(f"Extracted tweet text: {tweet_text[:100]}...")  # デバッグ用

        return {
            'url': url,
            'username': username,
            'tweet_id': tweet_id,
            'text': tweet_text[:500],  # 長めに取得（Teamsカードで表示調整）
            'date': email.get('date', ''),
            'email_id': email.get('id', '')
        }


# 不要なNewsCollectorとNewsFilterクラスは削除済み

class TextRewriter:
    """LLMを使用してテキストを魅力的に書き換え"""

    def __init__(self, config: Config):
        self.config = config
        self.endpoint = config.llm_endpoint
        self.model = config.llm_model

    def rewrite_text(self, original_text: str) -> str:
        """
        元のテキストを著作権に配慮しつつ魅力的に書き換える
        事実関係は厳密に保持する
        """
        if not original_text or original_text.strip() == "[メディアのみの投稿]":
            return original_text

        if not self.endpoint:
            logger.warning("LLM endpoint not configured, using original text")
            return original_text

        try:
            # システムプロンプト
            system_prompt = """あなたはTwitterで話題を紹介する人です。
元の内容を、短く魅力的な紹介ツイートに変換してください：

ルール：
1. 事実・数値は正確に保持（変えない・減らさない・増やさない）
2. 元のツイートを140文字以内で簡潔に紹介
3. 「〜だって」「〜らしい」「〜みたい」など口語的表現OK
4. 絵文字を効果的に使用
5. 興味を引く一言から始める
6. ハッシュタグは禁止"""

            # ユーザープロンプト
            user_prompt = f"""これを短く紹介：

{original_text}

紹介ツイート："""

            # リクエストボディの作成
            request_body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }

            # LLMへのリクエスト
            response = requests.post(
                self.endpoint,
                headers={"Content-Type": "application/json"},
                json=request_body,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    rewritten_text = result["choices"][0]["message"]["content"].strip()
                    logger.info("Text successfully rewritten by LLM")
                    return rewritten_text
                else:
                    logger.warning("Unexpected LLM response format")
                    return original_text
            else:
                logger.error(f"LLM request failed with status {response.status_code}: {response.text}")
                return original_text

        except requests.exceptions.Timeout:
            logger.error("LLM request timeout")
            return original_text
        except Exception as e:
            logger.error(f"Error rewriting text with LLM: {e}")
            return original_text

class TeamsPublisher:
    """X共有をMicrosoft Teamsに投稿"""

    def __init__(self, config: Config):
        self.config = config
        self.text_rewriter = TextRewriter(config)

    def create_x_share_card(self, x_info: Dict) -> Dict:
        """X共有用のAdaptive Card作成"""

        # テキストが空の場合
        original_text = x_info['text'] if x_info['text'] else "[メディアのみの投稿]"

        # LLMでテキストを書き換え
        text_display = self.text_rewriter.rewrite_text(original_text)

        # 書き換えが失敗した場合は元のテキストを使用
        if not text_display:
            text_display = original_text

        # Adaptive Cardで改行を表示するため、\nを\n\nに変換（Markdownでの改行）
        # また、TeamsのAdaptive Cardでは2つの改行が必要
        text_display = text_display.replace('\n', '\n\n')

        # 現在時刻を取得（JST）
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        time_str = now.strftime("%Y/%m/%d %H:%M:%S")

        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🐦 AI News form X - {time_str}",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "Accent"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"@{x_info['username']} の投稿に基づくAI紹介文",
                            "size": "Medium",
                            "color": "Good",
                            "spacing": "Small"
                        },
                        {
                            "type": "TextBlock",
                            "text": text_display,
                            "wrap": True,
                            "size": "Medium",
                            "spacing": "Medium"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Xで開く 🔗",
                            "url": x_info['url']
                        }
                    ]
                }
            }]
        }

    def post_to_teams(self, x_info: Dict) -> bool:
        """Teamsに投稿"""

        card = self.create_x_share_card(x_info)

        if self.config.dry_run:
            logger.info(f"DRY RUN - Would post to Teams: @{x_info['username']} - {x_info['text'][:50]}...")
            return True

        try:
            response = requests.post(
                self.config.teams_webhook_url,
                json=card,
                timeout=10
            )

            if response.status_code in [200, 202, 1]:
                logger.info(f"Posted to Teams: @{x_info['username']} - {x_info['tweet_id']}")
                return True
            else:
                logger.error(f"Failed to post to Teams: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error posting to Teams: {e}")
            return False


def main():
    """メイン処理"""

    # logger.info("=== X Gmail Share to Teams Bridge Started ===")  # 毎分は不要

    config = Config()

    if config.dry_run:
        logger.info("Running in DRY RUN mode")

    # Gmail認証
    gmail = GmailClient(config)
    if not gmail.authenticate():
        logger.error("Gmail authentication failed")
        return 1

    # X共有メールを検索
    emails = gmail.search_x_share_emails()

    if not emails:
        # logger.info("No X share emails found")  # 毎分は不要
        return 0

    # パーサーとパブリッシャー初期化
    parser = XShareParser()
    publisher = TeamsPublisher(config)

    posted_count = 0

    # 各メールを処理
    for email in emails:
        logger.info(f"Processing email: {email.get('subject', '')[:50]}...")

        # デバッグ：メール内容全文を出力
        logger.info("=" * 60)
        logger.info("【メール内容全文】")
        logger.info("=" * 60)
        logger.info(f"Subject: {email.get('subject', '')}")
        logger.info(f"Date: {email.get('date', '')}")
        logger.info("Body:")
        logger.info(email.get('body', ''))
        logger.info("=" * 60)

        # X情報を抽出
        x_info = parser.extract_x_info(email)

        if not x_info:
            logger.warning("Could not extract X info from email")
            continue

        # デバッグ：投稿内容全文を出力
        logger.info("=" * 60)
        logger.info("【Teams投稿内容】")
        logger.info("=" * 60)
        logger.info(f"URL: {x_info['url']}")
        logger.info(f"Username: @{x_info['username']}")
        logger.info(f"Tweet ID: {x_info['tweet_id']}")
        logger.info(f"Text:\n{x_info['text']}")
        logger.info("=" * 60)

        # Teamsに投稿
        if publisher.post_to_teams(x_info):
            posted_count += 1

            # 成功したら既読にする
            if config.mark_as_read:
                gmail.mark_as_read(email['id'])

    if posted_count > 0:
        logger.info(f"Posted {posted_count} X shares to Teams")
    return 0 if posted_count > 0 else 1

if __name__ == "__main__":
    exit(main())