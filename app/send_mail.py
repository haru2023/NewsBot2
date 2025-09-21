# send_mail.py
import os
import requests
import logging
from flask import Flask, request, Response, stream_with_context
from datetime import datetime
import pytz
import threading
import json
import re
import io

app = Flask(__name__)

# 日本のタイムゾーンを設定
japan_tz = pytz.timezone('Asia/Tokyo')

from util.util import get_next_request_id, get_client_app_name

# log
from util.log import setup_logger, log_request, log_response
logger = setup_logger(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def send_mail(path):
    """
    リクエストをプロキシする主要関数
    各種サービスへのリクエストを適切に転送し、レスポンスを返す
    """
    # リクエストIDを生成
    request_id = get_next_request_id()
    # ストリーミングリクエストかどうかを確認
    client_name = get_client_app_name(request)
    # リクエストのログを記録
    is_confidential = log_request(request_id, request, client_name)
    # リクエスト検証
    is_valid, error_message = validate_request(request, path)
    if not is_valid:
        response = Response(json.dumps({ "content": error_message }, ensure_ascii=False), status=400, headers=[('Content-Type', 'application/json')])
        log_response(request_id, response, is_confidential)
        return response

    # レスポンスオブジェクトの初期化
    response = None
    try:
        response = Response(f"hello", status=200)
        log_response(request_id, response, is_confidential)
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"[ERROR] {request_id} - エラーが発生しました: {str(e)}")
        return Response(f"Error: {str(e)}", status=500)

if os.getenv('ENV', '').lower() == 'dev':
    from util.debug import attach_debugger
    attach_debugger(port=5684)

def validate_request(request, path):
    """
    リクエストの検証を行い、有効なリクエストかどうかを確認する
    Args:
        request: Flaskのリクエストオブジェクト
        path: リクエストパス
    Returns:
        (bool, str): 検証結果（True/False）とエラーメッセージ（エラーがない場合はNone）
    """
    return True, None

if __name__ == '__main__':
    app.run()
