"""Seek 桌面版入口：在后台线程启动本地服务，并用系统 WebView 打开窗口。"""

import argparse
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request

APP_TITLE = "Seek"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _setup_logging(data_dir) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "seek.log"
    # 打包后的窗口程序没有控制台，stdout/stderr 为 None，需要重定向，否则日志输出会报错
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def _start_server(port: int):
    import uvicorn

    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started:
        if not thread.is_alive() or time.time() > deadline:
            raise RuntimeError("本地服务启动失败，详见日志")
        time.sleep(0.05)
    return server, thread


def _self_test(base_url: str) -> None:
    """打包后的冒烟测试：确认服务、界面与依赖都能正常加载。"""
    for path in ("/api/health", "/api/presets", "/api/settings", "/"):
        with urllib.request.urlopen(base_url + path, timeout=10) as resp:
            assert resp.status == 200, path
    # 向量库与 Chroma 原生模块
    from app.config import get_settings
    from app.embeddings import HashEmbeddingFunction
    from app.vectorstore import VectorStore
    import chromadb

    store = VectorStore(chromadb.EphemeralClient(), "selftest", HashEmbeddingFunction())
    assert store.companies() == {}
    if sys.platform == "win32":
        # 窗口组件依赖 pythonnet 加载 .NET 程序集，这一步最容易因系统安全策略失败
        import clr  # noqa: F401
        from System import Environment  # noqa: F401
    print(f"self-test ok (data dir: {get_settings().data_dir})")


def _run_in_browser(url: str) -> None:
    import webbrowser

    webbrowser.open(url)
    _message_box(
        "Seek 窗口组件无法启动，已改为在浏览器中打开。\n\n"
        f"地址：{url}\n\n使用期间请不要关闭这个提示框；点「确定」会退出 Seek。"
    )


def _message_box(text: str) -> None:
    """阻塞显示提示框；关闭提示框即退出。非 Windows 系统退化为等待服务线程。"""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, APP_TITLE, 0x40)
    else:
        logging.warning(text)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


def _run_self_test(port: int) -> None:
    server, thread = _start_server(port or _free_port())
    try:
        _self_test(f"http://127.0.0.1:{server.config.port}")
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def main() -> None:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--server", action="store_true", help="只启动本地服务，不打开窗口")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--self-test", action="store_true", help="启动服务并自检后退出")
    args = parser.parse_args()

    from app.config import get_settings

    _setup_logging(get_settings().data_dir)
    if args.self_test:
        # 打包后的窗口程序遇到未捕获异常会弹出对话框，CI 中会卡住，因此自检失败时直接以非零码退出
        try:
            _run_self_test(args.port)
        except Exception:  # noqa: BLE001
            logging.exception("self-test failed")
            os._exit(1)
        return

    port = args.port or _free_port()
    server, thread = _start_server(port)
    url = f"http://127.0.0.1:{port}/"
    logging.info("Seek running at %s", url)

    if args.server:
        print(f"Seek running at {url}", flush=True)
        try:
            thread.join()
        except KeyboardInterrupt:
            server.should_exit = True
        return

    try:
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True  # 允许导出 Markdown / JSON
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # 来源链接用系统浏览器打开
        webview.create_window(APP_TITLE, url, width=1240, height=840, min_size=(860, 600))
        webview.start(private_mode=False, storage_path=str(get_settings().data_dir / "webview"))
    except Exception:  # noqa: BLE001 - 窗口组件不可用时退回浏览器，而不是直接崩溃
        logging.exception("failed to open desktop window, falling back to browser")
        _run_in_browser(url)
    server.should_exit = True
    thread.join(timeout=5)
    os._exit(0)  # 确保后台线程（如 Chroma）不会阻止退出


if __name__ == "__main__":
    main()
