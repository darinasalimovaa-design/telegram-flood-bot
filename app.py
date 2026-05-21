import atexit
import asyncio
from concurrent.futures import TimeoutError
from threading import Lock
from threading import Thread

from flask import Flask, Response, abort, request

from bot import BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_SECRET, configure_webhook, process_update

app = Flask(__name__)

_startup_lock = Lock()
_started = False
_event_loop = asyncio.new_event_loop()


def _loop_runner():
    asyncio.set_event_loop(_event_loop)
    _event_loop.run_forever()


_loop_thread = Thread(target=_loop_runner, daemon=True)
_loop_thread.start()


def _run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
    try:
        return future.result(timeout=20)
    except TimeoutError:
        future.cancel()
        raise


def _shutdown_loop():
    if _event_loop.is_running():
        _event_loop.call_soon_threadsafe(_event_loop.stop)
    _loop_thread.join(timeout=1)


atexit.register(_shutdown_loop)


def ensure_started():
    global _started
    if _started:
        return
    with _startup_lock:
        if _started:
            return
        _run_async(configure_webhook())
        _started = True


@app.get("/")
def healthcheck():
    return Response("ok", status=200)


@app.post(WEBHOOK_PATH)
def telegram_webhook():
    if not BOT_TOKEN:
        abort(500, description="BOT_TOKEN is not set")

    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != WEBHOOK_SECRET:
            abort(403)

    if not request.is_json:
        abort(400, description="Request must be application/json")

    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Malformed JSON payload")

    try:
        ensure_started()
        _run_async(process_update(payload))
    except TimeoutError:
        abort(504, description="Webhook update processing timeout")
    return Response("ok", status=200)
