# log.py
import os
import json
import re
import logging
from datetime import datetime
import pytz
import base64
import requests
from flask import Response
from typing import Union, Dict, Any, Tuple

japan_tz = pytz.timezone('Asia/Tokyo')

class JapanTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, japan_tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

# additional ロガーをファイル内でのみ使用するグローバル変数として定義
_additional_logger = None

def setup_logger(name):
    # ロガーの作成
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # 既存のハンドラをクリア（重複を防ぐ）
    logger.handlers.clear()
    # ファイルハンドラの設定
    import os
    log_path = "/app/app/logs/log.log" if os.path.exists("/app/app/logs") else "/workspace/NewsBot2/app/logs/log.log"
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    # ストリームハンドラの設定
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    # フォーマッタの設定
    formatter = JapanTimeFormatter('■■■■■■■■%(asctime)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    # ハンドラをロガーに追加
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    # additional ロガーを内部的に初期化
    global _additional_logger

    # additional 用ロガー
    _additional_logger = logging.getLogger(name + ".additional")
    _additional_logger.setLevel(logging.INFO)
    _additional_logger.handlers.clear()
    _additional_logger.propagate = True
    special_log_path = "/app/app/logs/Special.log" if os.path.exists("/app/app/logs") else "/workspace/NewsBot2/app/logs/Special.log"
    additional_handler = logging.FileHandler(special_log_path, encoding='utf-8')
    additional_handler.setLevel(logging.INFO)
    additional_handler.setFormatter(formatter)
    _additional_logger.addHandler(additional_handler)

    return logger

# ロガーの初期化
logger = setup_logger(__name__)

def _log_info(message, client_name=None):
    """
    内部用ログ出力関数。メインのロガーに加えて、クライアント名に応じた専用ロガーにも出力する。

    Args:
        message: ログメッセージ
        client_name: クライアント名 (ChatAI または chrome-AI)
    """
    if client_name == "ChatAI" and _additional_logger:
        _additional_logger.info(message)
    else:
        logger.info(message)

def _log_error(message, client_name=None):
    """
    内部用エラーログ出力関数。メインのロガーに加えて、クライアント名に応じた専用ロガーにも出力する。

    Args:
        message: ログメッセージ
        client_name: クライアント名 (ChatAI または chrome-AI)
    """
    if client_name == "ChatAI" and _additional_logger:
        _additional_logger.error(message)
    else:
        logger.info(message)

def log_request(request_id: str, request, client_name = "") -> bool:
    """
    リクエストのログを記録する関数
    Args:
        request_id: リクエストの識別子
        request: リクエストオブジェクト
    """
    is_confidential = False
    name = "UNKN"
    if   client_name == "ChatAI"    : name = "CHAT"
    elif client_name == "chrome-AI" : name = "CHRM"
    method = request.method
    url = request.url
    headers = dict(request.headers)
    body = request.get_data()
    truncated_body, is_confidential = parse_and_truncate_body(body)
    _log_info(
        f"[REQ_{name}] {request_id} - {method} {url} "
        f"HEADER:{headers} BODY:{truncated_body}",
        client_name
    )
    return is_confidential


def log_response(request_id: str, resp: Union[Response, requests.Response], is_confidential: bool = False) -> None:
    """
    レスポンスのログを記録する関数
    Args:
        request_id: リクエストの識別子
        resp: FlaskのResponse オブジェクトまたはrequestsのResponseオブジェクト
    """
    if resp is None:
        logger.info(f"[RESP] {request_id} - Response is None")
        return

    status_code = resp.status_code
    headers = dict(resp.headers)

    try:
        
        if isinstance(resp, Response):
            # Flask Response の場合
            response_data = json.loads(resp.get_data(as_text=True))
        else:
            # requests Response の場合
            response_data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text

        truncated_body, is_confidential = parse_and_truncate_body(response_data, is_confidential)
        logger.info(
            f"[RESP] {request_id} - {status_code} "
            f"HEADER:{headers} BODY:{truncated_body}"
        )
    except json.JSONDecodeError:
        # JSONでないレスポンスの場合
        logger.info(
            f"[RESP] {request_id} - {status_code} "
            f"HEADER:{headers} BODY: Non-JSON response"
        )
    except Exception as e:
        logger.error(
            f"[RESP] {request_id} - Error processing response: {str(e)}"
        )

def parse_and_truncate_body(body: Union[str, bytes, Dict], is_confidential: bool = False) -> Tuple[str, bool]:
    """
    ボディをパースし、長い値を切り詰める
    Args:
        body: 処理対象のボディデータ
    Returns:
        処理済みのボディ文字列
    """
    try:
        # すでに辞書の場合はそのまま使用
        if isinstance(body, dict):
            body_dict = body
        else:
            # 文字列化してJSONパース
            if isinstance(body, bytes):
                body = body.decode('utf-8')
            body_dict = json.loads(body)
        # 長い値を切り詰める
        is_confidential = body_dict.get('is_alt', is_confidential)
        truncated_dict = truncate_long_values("root", body_dict, is_confidential, max_length=100)
        return json.dumps(truncated_dict, ensure_ascii=False, indent=2), is_confidential
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        # JSONでない場合は文字列として返す
        return str(body), is_confidential

def truncate_long_values(key: str, value: Any, is_confidential: bool = False, max_length: int = 100) -> Any:
    """
    辞書内の文字列値を再帰的にチェックし、長い値を切り詰める
    Args:
        key: 現在処理中のキー名
        value: 処理対象のデータ（dict, list, または基本型）
        is_confidential: 機密データかどうか
        max_length: 切り詰める最大長
    Returns:
        処理済みのデータ
    """
    # is_confidential の場合、queryなど、AIへの入出力はログに残さない
    sensitive_keys = ['message', 'messages', 'content', 'prompt', 'query', 'choices']
    if is_confidential and key in sensitive_keys:
        return f"({key} is confidential)"

    if isinstance(value, dict):
        return {k: truncate_long_values(k, v, is_confidential, max_length) for k, v in value.items()}
    elif isinstance(value, list):
        return [truncate_long_values(key, item, is_confidential, max_length) for item in value]
    elif isinstance(value, str):
        # content_typeやfilenameなど、システム的な値は切り詰めない
        if any(v in value.lower() for v in ['content-type', '.xlsx', '.pdf', '.doc']):
            return value
        # 半角英数字のみ、またはbase64エンコードされた文字列かチェック
        if (re.match(r'^[a-zA-Z0-9]+$', value) or is_base64(value)) and len(value) > max_length:
            return value[:max_length] + "...(truncated)"
        return value
    return value

def is_base64(s: str) -> bool:
    """
    文字列がbase64エンコードされているかチェックする
    Args:
        s: チェック対象の文字列
    Returns:
        bool: base64エンコードされていればTrue
    """
    # base64の文字パターンチェック
    if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', s):
        return False
    # 長さチェック（4の倍数）
    if len(s) % 4 != 0:
        return False
    try:
        # デコードを試みる
        decoded = base64.b64decode(s)
        # バイナリデータとしてデコード可能か
        return True
    except Exception:
        return False
