import os
import asyncio
from flask import Flask, request, abort

from aiogram.types import Update

from bot import get_bot, get_dispatcher, get_webhook_secret

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram-webhook")
WEBHOOK_SECRET = get_webhook_secret()

bot = get_bot()
dp = get_dispatcher()


async def process_update(data: dict):
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)


@app.route("/")
def index():
    return "OK", 200


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != WEBHOOK_SECRET:
        abort(403)

    data = request.get_json(force=True, silent=False)
    asyncio.run(process_update(data))
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
