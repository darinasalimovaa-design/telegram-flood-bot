import asyncio
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
    return asyncio.run_coroutine_threadsafe(coro, _event_loop).result()


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

    payload = request.get_json(silent=True)
    if not payload:
        abort(400, description="Invalid JSON payload")

    ensure_started()
    _run_async(process_update(payload))
    return Response("ok", status=200)
