#!/usr/bin/env python3
"""
LLMテキスト書き換え機能のテスト
"""

import os
import sys
import json
import requests
from pathlib import Path

# app ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent / 'app'))

def test_llm_connection():
    """LLMエンドポイントへの接続テスト"""
    endpoint = os.getenv("LLM_ENDPOINT")
    model = os.getenv("LLM_MODEL")

    print(f"LLM Endpoint: {endpoint}")
    print(f"LLM Model: {model}")

    if not endpoint:
        print("エラー: LLM_ENDPOINTが設定されていません")
        return False

    # テスト用のシンプルなリクエスト
    test_request = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Hello, respond with 'OK' if you receive this."}
        ],
        "temperature": 0.7,
        "max_tokens": 10
    }

    try:
        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=test_request,
            timeout=10
        )

        if response.status_code == 200:
            print("✓ LLMエンドポイントに正常に接続できました")
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                print(f"  レスポンス: {result['choices'][0]['message']['content']}")
            return True
        else:
            print(f"✗ LLMエンドポイントへのリクエスト失敗: Status {response.status_code}")
            print(f"  エラー: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("✗ LLMエンドポイントに接続できません")
        print(f"  エンドポイント {endpoint} が起動していることを確認してください")
        return False
    except requests.exceptions.Timeout:
        print("✗ LLMエンドポイントへのリクエストがタイムアウトしました")
        return False
    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        return False

def test_text_rewriting():
    """テキスト書き換え機能のテスト"""
    from send_tweet import TextRewriter, Config

    config = Config()
    rewriter = TextRewriter(config)

    # テストケース
    test_cases = [
        "政府は本日、新しい経済対策を発表しました。総額は約30兆円規模となる見込みです。",
        "東京都の新型コロナウイルス新規感染者数は、本日1234人でした。前週同曜日と比べて200人増加しています。",
        "明日から全国的に気温が上昇し、東京では最高気温35度の猛暑日となる予報です。"
    ]

    print("\n=== テキスト書き換えテスト ===")
    for i, original in enumerate(test_cases, 1):
        print(f"\nケース {i}:")
        print(f"【元のテキスト】\n{original}")

        rewritten = rewriter.rewrite_text(original)

        print(f"【書き換え後】\n{rewritten}")
        print("-" * 50)

if __name__ == "__main__":
    print("=" * 60)
    print("LLMテキスト書き換え機能のテスト")
    print("=" * 60)

    # LLM接続テスト
    if test_llm_connection():
        # テキスト書き換えテスト
        test_text_rewriting()
    else:
        print("\nLLMエンドポイントに接続できないため、テストを中止します")
        print("\n対処方法:")
        print("1. Llama.cppサーバーが起動していることを確認")
        print("2. LLM_ENDPOINTの設定が正しいことを確認")
        print("3. ファイアウォール設定を確認")