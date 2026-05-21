import asyncio
from threading import Lock

from flask import Flask, Response, abort, request

from bot import BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_SECRET, configure_webhook, process_update

app = Flask(__name__)

_startup_lock = Lock()
_started = False


def ensure_started():
    global _started
    if _started:
        return
    with _startup_lock:
        if _started:
            return
        asyncio.run(configure_webhook())
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
    asyncio.run(process_update(payload))
    return Response("ok", status=200)
