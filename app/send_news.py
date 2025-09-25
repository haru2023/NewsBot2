#!/usr/bin/env python3
"""
AI News Bot for Microsoft Teams
Collects and posts AI-related news to Teams channel via webhook
"""

import os
import json
import pytz
import feedparser
import requests
import re
from datetime import datetime, timedelta
from typing import List, Dict
from dataclasses import dataclass
from dateutil import parser

# Import setup_logger from util.log
from util.log import setup_logger

# Setup logging
logger = setup_logger(__name__)

# Configuration
@dataclass
class Config:
    """Configuration settings"""
    teams_webhook_url: str = os.getenv("TEAMS_WEBHOOK_URL", "")
    llm_endpoint: str = os.getenv("LLM_ENDPOINT", "http://192.168.131.193:8008/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    max_news_items: int = int(os.getenv("MAX_NEWS_ITEMS", "3"))
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"

# RSS Feed Sources - Japanese AI/Tech News
RSS_FEEDS = [
    # 日本のAI・技術ニュースサイト
    ("ITmedia AI+ RSS", "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"),
    ("ITmedia NEWS AI", "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml"),
    ("ITmedia エンタープライズ", "https://rss.itmedia.co.jp/rss/2.0/enterprise.xml"),
    ("@IT", "https://rss.itmedia.co.jp/rss/2.0/ait.xml"),
    ("@IT Security", "https://rss.itmedia.co.jp/rss/2.0/ait_security.xml"),
    ("GIGAZINE", "https://gigazine.net/news/rss_2.0/"),
    ("ZDNet Japan", "https://feeds.japan.zdnet.com/rss/zdnet/all.rdf"),
    ("CNET Japan", "https://feeds.japan.cnet.com/rss/cnet/all.rdf"),
    ("Publickey", "https://www.publickey1.jp/atom.xml"),
    ("はてなブックマーク テクノロジー", "https://b.hatena.ne.jp/hotentry/it.rss"),
    ("Developers.IO", "https://dev.classmethod.jp/feed/"),
    ("Qiita トレンド", "https://qiita.com/popular-items/feed"),
    ("Zenn トレンド", "https://zenn.dev/feed"),
]

class NewsCollector:
    """Collects news from various RSS feeds"""

    def __init__(self, feeds: List[tuple], hours_back: int = 3, max_entries_per_feed: int = 30):
        self.feeds = feeds
        self.hours_back = hours_back  # 何時間前までの記事を取得するか
        self.max_entries_per_feed = max_entries_per_feed  # 各フィードから取得する最大記事数

    def fetch_articles(self) -> List[Dict]:
        """Fetch articles from all configured RSS feeds"""
        all_articles = []

        # 現在時刻から指定時間前までを取得対象とする
        jst = pytz.timezone('Asia/Tokyo')
        cutoff_time = datetime.now(jst) - timedelta(hours=self.hours_back)

        # 各フィードの統計を保存
        feed_stats = {}

        for source_name, feed_url in self.feeds:
            try:
                logger.info(f"Fetching from {source_name}...")
                feed = feedparser.parse(feed_url)
                articles_added = 0

                # ① 各RSS_FEEDから取得した生データをログ出力
                logger.info(f"  Raw feed data from {source_name}:")
                logger.info(f"    Feed entries count: {len(feed.entries)}")
                if len(feed.entries) > 0:
                    logger.info(f"    Sample entry (first): {json.dumps(dict(feed.entries[0]), indent=2, default=str, ensure_ascii=False)[:1000]}...")

                total_in_feed = 0  # フィードから取得した総記事数
                recent_count = 0   # 指定時間内の記事数

                for entry in feed.entries[:self.max_entries_per_feed]:  # 環境変数で制御
                    total_in_feed += 1
                    # 公開日時のパース
                    published_str = entry.get("published", "")
                    if not published_str:
                        # 公開日時が空の場合はスキップ
                        continue

                    try:
                        published_dt = parser.parse(published_str)
                        if published_dt.tzinfo is None:
                            published_dt = jst.localize(published_dt)

                        # 指定時間より古い記事はスキップ
                        if published_dt < cutoff_time:
                            continue
                    except:
                        continue  # パースできない場合は含めない

                    article = {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": source_name,
                        "published": published_str,
                        "summary": entry.get("summary", "")[:500] if entry.get("summary") else ""
                    }
                    logger.info(f'{article["title"]=}, {article["url"]=}, {article["source"]=}, {article["published"]=}')
                    all_articles.append(article)
                    articles_added += 1
                    recent_count += 1

                logger.info(f"  Fetched {articles_added} articles from {source_name} (last {self.hours_back} hours)")

                feed_stats[source_name] = {
                    'total_fetched': total_in_feed,
                    'recent_count': recent_count
                }

            except Exception as e:
                logger.error(f"Error fetching from {source_name}: {e}")
                feed_stats[source_name] = {
                    'total_fetched': 0,
                    'recent_count': 0
                }

        # Log summary of articles collected per source
        logger.info("=" * 60)
        logger.info("ARTICLES COLLECTED PER SOURCE:")
        source_counts = {}
        for article in all_articles:
            source = article['source']
            source_counts[source] = source_counts.get(source, 0) + 1

        for source_name, _ in self.feeds:
            count = source_counts.get(source_name, 0)
            logger.info(f"  {source_name}: {count} articles")

        logger.info("=" * 60)
        logger.info(f"Total articles collected: {len(all_articles)}")

        # source_counts と feed_stats を保存して後で使用
        self.source_counts = source_counts
        self.feed_stats = feed_stats

        return all_articles

class NewsFilter:
    """Filters news using LLM for relevance"""

    def __init__(self, config: Config):
        self.config = config

    def filter_articles(self, articles: List[Dict]) -> List[Dict]:
        """Filter articles using LLM for relevance"""

        if not articles:
            return []

        # Remove duplicate titles
        seen_titles = set()
        unique_articles = []
        for article in articles:
            title = article.get('title', '').strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(article)

        logger.info(f"Removed {len(articles) - len(unique_articles)} duplicate articles based on title")
        articles = unique_articles

        # LLMに送る記事数の上限（環境変数で設定可能、デフォルト40）
        max_articles_to_llm = int(os.getenv('MAX_ARTICLES_TO_LLM', '40'))

        # Prepare article list for LLM
        article_list = "\n".join([
            f"{i+1}. {art['title']} (from {art['source']})"
            for i, art in enumerate(articles[:max_articles_to_llm])  # Limit to prevent context overflow
        ])

        # ② LLMに送信するプロンプト（全文）をログ出力
        prompt = f"""以下の記事リストから、AIコンサルタント・弁護士向けに特に関連性の高いニュースを選んでください。

優先度の高いカテゴリ（専門性重視）:
1. 【最優先】法務・コンプライアンス関連
   - AI規制・ガバナンス（EU AI Act、日本のAIガイドライン改訂など）
   - 個人情報保護（APPI、GDPR）・プライバシー関連の動向
   - クラウドセキュリティ認証（ISO27001、ISMAP、SOC2、FedRAMP）の更新
   - セキュリティインシデント・脆弱性（CVE、データ漏洩、不正アクセス、サプライチェーン攻撃）
   - 法律業界でのAI活用事例（契約書レビュー、法的文書自動生成、判例検索）   

2. 【高優先】実務に直結するAIツール・技術
   - 業務における生成AI活用の具体的事例
   - ローカル生成 AI（SLM/VLM/OCR/音声認識等）の新機能・精度向上・比較
   - Claude Code、MCPなどAI開発支援ツールの更新・Tips
   - AIエージェント評価・統合ツール（Dify、n8n、LangGraph、CrewAI）

3. 【高優先】SLM（小規模言語モデル）の進化
   - 軽量・高速・省電力なAIモデル（Phi、Gemma、富士通Takane、NEC cotomi、Qwen等）
   - エッジデバイスでのAI実行技術
   - 特定タスク特化型モデル（法務、医療、金融向け）

4. 【中優先】インフラ・開発環境
   - Docker、WSL2、Dev Container関連の重要更新
   - GPU最適化・クラウドコンピューティング（AWS、Azure、GCP）
   - Teams、Slack等のコラボツール（特に法律事務所・テレワーク活用）
   - Git/GitHub、テスト自動化（Playwright等）の新機能

5. 【参考】技術スタック関連
   - Python、Flask、FastAPI、Uvicornの重要更新
   - Elasticsearch、MySQLの新機能・セキュリティ更新
   - Nginx、Llama.cppの最適化技術

記事リスト:
{article_list}

選択基準（重要度順）:
1. 法的リスク・コンプライアンスへの影響がある
2. 法律事務所・コンサル業務の効率化に直結する
3. 具体的な製品名・バージョン・実装例が明記されている
4. 1か月以内に導入・検証可能な実用的な内容

最大{self.config.max_news_items}個の記事を選んで返してください。"""

        # LLMに送信するプロンプト全文をログ出力
        logger.info("="*80)
        logger.info("LLM REQUEST - Full Prompt:")
        logger.info("="*80)
        logger.info(prompt)
        logger.info("="*80)

        # Define JSON schema for structured output
        json_schema = {
            "type": "object",
            "properties": {
                "selected_articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "number": {"type": "integer"},
                            "relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
                            "category": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["number", "relevance_score", "category", "reason"]
                    }
                }
            },
            "required": ["selected_articles"]
        }

        try:
            response = requests.post(
                self.config.llm_endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer no-key"
                },
                json={
                    "model": self.config.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an AI news curator specializing in development tools and AI technologies. Focus on practical, immediately useful information for SaaS development teams."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 3000,
                    "response_format": {
                        "type": "json_object",
                        "schema": json_schema
                    }
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()

                # ③ LLMから取得したデータ（全文）をログ出力
                logger.info("="*80)
                logger.info("LLM RESPONSE - Full Response:")
                logger.info("="*80)
                logger.info(json.dumps(result, indent=2, ensure_ascii=False))
                logger.info("="*80)

                content = result['choices'][0]['message']['content']

                parsed_response = json.loads(content)
                filtered_indices = parsed_response.get('selected_articles', [])

                # Sort by relevance score
                filtered_indices.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

                # Map back to original articles
                filtered_articles = []
                for item in filtered_indices[:self.config.max_news_items]:
                    idx = item['number'] - 1
                    if 0 <= idx < len(articles[:max_articles_to_llm]):
                        article = articles[idx].copy()
                        article['relevance_score'] = item.get('relevance_score', 0)
                        article['category'] = item.get('category', 'General')
                        article['reason'] = item.get('reason', '')
                        filtered_articles.append(article)

                logger.info(f"Filtered to {len(filtered_articles)} relevant articles")

                # ④ サマリー（②で実際に送られた記事の詳細）
                logger.info("")
                logger.info("="*80)
                logger.info("FILTERING SUMMARY:")
                logger.info("="*80)
                logger.info(f"  Articles sent to LLM for evaluation: {len(articles[:max_articles_to_llm])}")
                logger.info(f"  Articles selected by LLM: {len(filtered_articles)}")
                logger.info("")
                logger.info("  Selected articles detail:")
                logger.info("  " + "-"*50)

                # 選択された記事をソース別に集計
                selected_by_source = {}
                for article in filtered_articles:
                    source = article['source']
                    if source not in selected_by_source:
                        selected_by_source[source] = []
                    selected_by_source[source].append(article)

                for i, article in enumerate(filtered_articles, 1):
                    logger.info(f"  {i}. [{article.get('category', 'N/A'):15}] Score: {article.get('relevance_score', 0):.2f}")
                    logger.info(f"     Title: {article['title'][:80]}..." if len(article['title']) > 80 else f"     Title: {article['title']}")
                    logger.info(f"     Source: {article['source']}")
                    logger.info(f"     Reason: {article.get('reason', 'N/A')[:100]}..." if len(article.get('reason', '')) > 100 else f"     Reason: {article.get('reason', 'N/A')}")
                    logger.info("")

                logger.info("  " + "-"*50)
                logger.info("  Selected articles by source:")
                for source_name, articles in selected_by_source.items():
                    logger.info(f"    {source_name}: {len(articles)} articles")
                logger.info("="*80)

                return filtered_articles

            else:
                logger.error(f"LLM Error: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Error filtering articles: {e}")

        # Fallback: return top articles if LLM fails
        return articles[:self.config.max_news_items]

class TeamsPublisher:
    """Publishes news to Microsoft Teams"""

    def __init__(self, config: Config):
        self.config = config

    def format_published_date(self, published_str: str) -> str:
        """Format published date to YY/MM/DD HH:mm format"""
        if not published_str:
            return ""
        try:
            # Parse the date string
            dt = parser.parse(published_str)
            # Format to YY/MM/DD HH:mm
            return dt.strftime("%y/%m/%d %H:%M")
        except:
            # Return original if parsing fails
            return published_str

    def create_news_card(self, article: Dict, index: int) -> Dict:
        """Create an Adaptive Card for a news article"""

        # Emoji mapping for categories
        category_emoji = {
            "SLM/VLM": "🤖",
            "AI Coding Agent": "💻",
            "AI Agent": "🔧",
            "AIセキュリティ": "🔒",
            "Python": "🐍",
            "TypeScript": "📘",
            "音声認識": "🎤",
            "OCR": "👁️",
        }

        # Find matching emoji
        emoji = "📰"
        for key, value in category_emoji.items():
            if key in article.get('category', ''):
                emoji = value
                break

        # Format score as stars
        score = article.get('relevance_score', 0)
        if score >= 0.9:
            stars = "⭐⭐⭐⭐⭐"
        elif score >= 0.8:
            stars = "⭐⭐⭐⭐"
        elif score >= 0.7:
            stars = "⭐⭐⭐"
        elif score >= 0.5:
            stars = "⭐⭐"
        else:
            stars = "⭐"

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
                            "text": f"{emoji} AI News #{index}",
                            "size": "Medium",
                            "weight": "Bolder",
                            "color": "Accent"
                        },
                        {
                            "type": "TextBlock",
                            "text": article['title'],
                            "size": "Large",
                            "weight": "Bolder",
                            "wrap": True
                        },
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": f"📂 {article.get('category', 'General')}",
                                            "size": "Small",
                                            "color": "Good"
                                        }
                                    ]
                                },
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": self.format_published_date(article.get('published', '')),
                                            "size": "Small"
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": f"💡 {article.get('reason', 'AIに関連するニュースです')}",
                            "wrap": True,
                            "size": "Medium",
                            "spacing": "Small"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{article['source']}",
                            "size": "Small",
                            "color": "Attention",
                            "spacing": "Small"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "記事を読む 🔗",
                            "url": article['url']
                        }
                    ]
                }
            }]
        }

    def post_summary_card(self, total_articles: int, filtered_count: int) -> bool:
        """Post a summary card with today's statistics"""

        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        today = now.strftime("%Y-%m-%d %H:%M")

        card = {
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
                            "text": f"🤖 AI News Daily - {today}",
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "color": "Accent"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"本日のAIニュースをお届けします",
                            "size": "Medium",
                            "spacing": "Small"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "📊 収集記事数", "value": str(total_articles)},
                                {"title": "✅ 選択記事数", "value": str(filtered_count)},
                                {"title": "🎯 対象", "value": "法律事務所内 AI Product 開発チーム"},
                                {"title": "🔍 フォーカス", "value": "セキュリティ, AI/ML, Coding Agent, LangGraph等"}
                            ]
                        }
                    ]
                }
            }]
        }

        if self.config.dry_run:
            logger.info("DRY RUN - Would post summary card")
            return True

        try:
            response = requests.post(
                self.config.teams_webhook_url,
                json=card,
                timeout=10
            )

            return response.status_code in [200, 202, 1]

        except Exception as e:
            logger.error(f"Error posting summary: {e}")
            return False

    def post_article(self, article: Dict, index: int) -> bool:
        """Post a single article to Teams"""

        card = self.create_news_card(article, index)

        if self.config.dry_run:
            logger.info(f"DRY RUN - Would post: {article['title']}")
            return True

        try:
            response = requests.post(
                self.config.teams_webhook_url,
                json=card,
                timeout=10
            )

            if response.status_code in [200, 202, 1]:
                logger.info(f"Posted: {article['title']}")
                return True
            else:
                logger.error(f"Failed to post: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error posting article: {e}")
            return False

    def create_combined_news_card(self, articles: List[Dict], total_collected: int) -> Dict:
        """Create a single Adaptive Card containing all news articles"""

        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        today = now.strftime("%Y-%m-%d %H:%M")

        # Create body sections for all articles
        body_sections = [
            {
                "type": "TextBlock",
                "text": f"🤖 AI News Daily - {today}",
                "size": "ExtraLarge",
                "weight": "Bolder",
                "color": "Accent"
            },
            {
                "type": "TextBlock",
                "text": f"本日のAIニュース {len(articles)}件をお届けします",
                "size": "Medium",
                "spacing": "Small"
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "📊 収集記事数", "value": str(total_collected)},
                    {"title": "✅ 選択記事数", "value": str(len(articles))},
                    {"title": "🎯 対象", "value": "法律事務所内 AI Product 開発チーム"}
                ]
            },
            {
                "type": "TextBlock",
                "text": "─" * 30,
                "separator": True,
                "spacing": "Medium"
            }
        ]

        # Add each article to the card
        for i, article in enumerate(articles, 1):
            # Emoji mapping for categories
            category_emoji = {
                "SLM/VLM": "🤖",
                "AI Coding Agent": "💻",
                "AI Agent": "🔧",
                "AIセキュリティ": "🔒",
                "Python": "🐍",
                "TypeScript": "📘",
                "音声認識": "🎤",
                "OCR": "👁️",
            }

            # Find matching emoji
            emoji = "📰"
            for key, value in category_emoji.items():
                if key in article.get('category', ''):
                    emoji = value
                    break

            # Format score as stars
            score = article.get('relevance_score', 0)
            if score >= 0.9:
                stars = "⭐⭐⭐⭐⭐"
            elif score >= 0.8:
                stars = "⭐⭐⭐⭐"
            elif score >= 0.7:
                stars = "⭐⭐⭐"
            elif score >= 0.5:
                stars = "⭐⭐"
            else:
                stars = "⭐"

            # Add article section
            body_sections.extend([
                {
                    "type": "TextBlock",
                    "text": f"{emoji} #{i} {article['title']}",
                    "size": "Medium",
                    "weight": "Bolder",
                    "wrap": True,
                    "color": "Accent"
                },
                {
                    "type": "ColumnSet",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": f"📂 {article.get('category', 'General')}",
                                    "size": "Small",
                                    "color": "Good"
                                }
                            ]
                        },
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": self.format_published_date(article.get('published', '')),
                                    "size": "Small"
                                }
                            ]
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": f"{article['source']}",
                                    "size": "Small",
                                    "color": "Attention"
                                }
                            ]
                        }
                    ]
                }
            ])

            # Add summary if available
            summary_text = article.get('summary', '').strip()
            if summary_text:
                # Remove HTML tags
                summary_text = re.sub(r'<[^>]+>', '', summary_text)
                # Remove multiple spaces and newlines
                summary_text = re.sub(r'\s+', ' ', summary_text).strip()

                # Limit summary length and add ellipsis if truncated
                max_length = 200
                if len(summary_text) > max_length:
                    summary_text = summary_text[:max_length] + "..."

                # Only add if there's still content after cleaning
                if summary_text:
                    body_sections.append({
                        "type": "TextBlock",
                        "text": summary_text,
                        "wrap": True,
                        "size": "Small",
                        "isSubtle": True,
                        "spacing": "Small"
                    })

            # Add action button
            body_sections.append({
                "type": "ActionSet",
                "actions": [
                    {
                        "type": "Action.OpenUrl",
                        "title": f"記事を読む 🔗",
                        "url": article['url']
                    }
                ]
            })

            # Add separator between articles (except for last one)
            if i < len(articles):
                body_sections.append({
                    "type": "TextBlock",
                    "text": "",
                    "separator": True,
                    "spacing": "Medium"
                })

        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "body": body_sections
                }
            }]
        }

    def publish_news(self, articles: List[Dict], total_collected: int = None) -> int:
        """Publish all news articles to Teams in a single message"""

        if not articles:
            logger.warning("No articles to publish")
            return 0

        if total_collected is None:
            total_collected = len(articles) * 3  # Fallback estimate

        # Create and post combined card
        combined_card = self.create_combined_news_card(articles, total_collected)

        if self.config.dry_run:
            logger.info(f"DRY RUN - Would post combined card with {len(articles)} articles")
            return len(articles)

        try:
            response = requests.post(
                self.config.teams_webhook_url,
                json=combined_card,
                timeout=10
            )

            if response.status_code in [200, 202, 1]:
                logger.info(f"Successfully posted combined card with {len(articles)} articles")
                return len(articles)
            else:
                logger.error(f"Failed to post combined card: {response.status_code}")
                return 0

        except Exception as e:
            logger.error(f"Error posting combined card: {e}")
            return 0

def main():
    """Main execution function"""

    logger.info("=== AI News Bot Started ===")

    # Load configuration
    config = Config()

    if config.dry_run:
        logger.info("Running in DRY RUN mode - no actual posts will be made")

    # Collect news
    hours_back = int(os.getenv('HOURS_BACK', '3'))  # デフォルト3時間前まで
    max_entries_per_feed = int(os.getenv('MAX_ENTRIES_PER_FEED', '30'))  # デフォルト30件
    collector = NewsCollector(RSS_FEEDS, hours_back=hours_back, max_entries_per_feed=max_entries_per_feed)
    articles = collector.fetch_articles()

    if not articles:
        logger.error("No articles collected")
        return 1

    # Filter news
    filter = NewsFilter(config)
    filtered_articles = filter.filter_articles(articles)

    if not filtered_articles:
        logger.warning("No relevant articles found after filtering")
        return 1

    # Calculate total collected articles before publishing
    total_collected = 0
    for source_name, _ in RSS_FEEDS:
        stats = collector.feed_stats.get(source_name, {'total_fetched': 0, 'recent_count': 0})
        total_collected += stats['recent_count']

    # Publish to Teams
    publisher = TeamsPublisher(config)
    published = publisher.publish_news(filtered_articles, total_collected)

    # ④ 実行サマリー
    logger.info("")
    logger.info("="*80)
    logger.info("【実行サマリー】")
    logger.info("="*80)

    # 収集サマリー
    logger.info("■ 記事収集")
    logger.info(f"  対象期間: 過去 {hours_back} 時間")
    logger.info(f"  RSSフィード数: {len(RSS_FEEDS)} 件")
    logger.info(f"  各フィード最大取得数: {max_entries_per_feed} 件")
    logger.info("")

    # フィード別詳細
    logger.info("  フィード別収集結果: (過去{0}時間内/取得総数)".format(hours_back))
    logger.info("  " + "-"*65)

    total_collected = 0
    total_fetched = 0
    for source_name, _ in RSS_FEEDS:
        stats = collector.feed_stats.get(source_name, {'total_fetched': 0, 'recent_count': 0})
        recent = stats['recent_count']
        fetched = stats['total_fetched']
        total_collected += recent
        total_fetched += fetched

        status = "✓" if recent > 0 else "✗"
        ratio_str = f"{recent:2}/{fetched:2}"
        logger.info(f"  {status} {source_name:40} : {ratio_str:7} 件")

    logger.info("  " + "-"*65)
    logger.info(f"  合計: {total_collected}/{total_fetched} 件収集")
    logger.info("")

    # 処理サマリー
    max_articles_to_llm = int(os.getenv('MAX_ARTICLES_TO_LLM', '40'))
    logger.info("■ 記事処理")
    logger.info(f"  収集記事数: {len(articles)} 件")
    logger.info(f"  LLMへ送信: {min(max_articles_to_llm, len(articles))} 件")
    logger.info(f"  LLMが選択: {len(filtered_articles)} 件")
    logger.info(f"  Teams投稿: {published} 件")
    logger.info("")

    # 実行結果
    logger.info("■ 実行結果")
    logger.info(f"  ステータス: {'成功 ✓' if published > 0 else '失敗 ✗'}")
    logger.info("="*80)

    logger.info(f"=== AI News Bot 完了 - {published}件の記事を投稿しました ===")
    return 0 if published > 0 else 1

if __name__ == "__main__":
    exit(main())