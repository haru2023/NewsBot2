# debug.py
from threading import Thread

def attach_debugger(port=5678):
    try:
        import debugpy
        debugpy.log_to("/app/logs/debugpy.log")
        import threading

        def wait_for_client():
            try:
                # すでにリッスンしているかチェック
                try:
                    debugpy.configure(python="/usr/local/bin/python")  # Pythonパスを明示的に指定
                    debugpy.listen(('0.0.0.0', port))
                    # 明示的に待機
                    debugpy.wait_for_client()
                except RuntimeError as e:
                    if "already" in str(e):
                        print("Debugpy already listening")
                    else:
                        raise
            except Exception as e:
                print(f"Debugger error: {e}")

        # 非同期でデバッガーを初期化
        debug_thread = threading.Thread(target=wait_for_client, daemon=True)
        debug_thread.start()
        return debug_thread

    except Exception as e:
        return None
