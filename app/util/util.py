# util.py
import re
import threading
import logging
import requests
import json
import os
from flask import request

# リクエストIDのカウンター
request_counter = 0
request_counter_lock = threading.Lock()

# ロガーの設定
from util.log import setup_logger
logger = setup_logger(__name__)

def get_next_request_id():
    global request_counter
    with request_counter_lock:
        request_counter += 1
        return f"{request_counter:06d}"  # 6桁の0埋め整数

def get_client_app_name(request):
    """クライアントアプリケーション名の取得"""
    try:
        if request.is_json:
            json_data = request.get_json()
            client_name = json_data.get('client_name', "")
            referer = request.headers.get('Referer', "")
            if client_name:
                return client_name
            elif 'query' in json_data:
                return "chrome-AI"
            elif 'messages' in json_data or "chatai" in referer:
                return "ChatAI"
    except Exception as e:
        logger.error(f"JSONの解析エラー: {str(e)}")
    return "Unknown"
