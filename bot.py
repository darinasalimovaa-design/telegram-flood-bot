import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv

from storage import load_config, load_data, save_data

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("flood_bot")

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

USER_STATE = {}


def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Подать заявку")
    kb.button(text="Мои заявки")
    kb.button(text="Отменить")
    kb.button(text="Инфо")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def cancel_inline():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отменить действие", callback_data="cancel_action")]])


def chat_choice_kb():
    cfg = load_config()
    kb = InlineKeyboardBuilder()
    kb.button(text=cfg["chats"]["chat1"]["title"], callback_data="choose_chat:chat1")
    kb.button(text=cfg["chats"]["chat2"]["title"], callback_data="choose_chat:chat2")
    kb.adjust(1)
    return kb.as_markup()


async def is_full(chat_key: str) -> bool:
    cfg = load_config()
    chat = cfg["chats"][chat_key]
    if chat["chat_id"] == 0:
        return False
    try:
        count = await bot.get_chat_member_count(chat["chat_id"])
        return count >= chat["member_limit"]
    except Exception:
        return False


async def send_admins(text: str, markup=None):
    cfg = load_config()
    if cfg.get("main_admin_id"):
        await bot.send_message(cfg["main_admin_id"], text, reply_markup=markup)
    if cfg.get("admin_group_id"):
        await bot.send_message(cfg["admin_group_id"], text, reply_markup=markup)


@dp.message(CommandStart())
async def start(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    await message.answer("Привет. Выбери действие в меню ниже.", reply_markup=main_menu())


@dp.message(Command("menu"))
async def menu(message: Message):
    await message.answer("Меню открыто.", reply_markup=main_menu())


@dp.message(F.text == "Инфо")
async def info(message: Message):
    cfg = load_config()
    text = (
        f"<b>{cfg['chats']['chat1']['title']}</b>: {cfg['chats']['chat1']['info_url']}\n"
        f"<b>{cfg['chats']['chat2']['title']}</b>: {cfg['chats']['chat2']['info_url']}"
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(F.text == "Подать заявку")
async def apply(message: Message):
    await message.answer("Выбери чат:", reply_markup=chat_choice_kb())


@dp.callback_query(F.data.startswith("choose_chat:"))
async def choose_chat(call: CallbackQuery):
    chat_key = call.data.split(":", 1)[1]
    if await is_full(chat_key):
        await call.message.answer("Этот чат заполнен. Выбери другой чат или дождись брони роли.")
        await call.answer()
        return
    cfg = load_config()
    chat = cfg["chats"][chat_key]
    USER_STATE[call.from_user.id] = {"chat_key": chat_key, "step": "role"}
    await call.message.answer(f"Сначала ознакомься с инфо: {chat['info_url']}\n\nТеперь введи желаемую роль:", reply_markup=cancel_inline())
    await call.answer()


@dp.callback_query(F.data == "cancel_action")
async def cancel_action(call: CallbackQuery):
    USER_STATE.pop(call.from_user.id, None)
    await call.message.answer("Действие отменено.", reply_markup=main_menu())
    await call.answer()


@dp.message(F.text)
async def text_router(message: Message):
    state = USER_STATE.get(message.from_user.id)
    if not state:
        return
    step = state.get("step")
    if step == "role":
        state["role"] = message.text
        state["step"] = "birth"
        await message.answer("Введи дату рождения (YYYY-MM-DD):", reply_markup=cancel_inline())
    elif step == "birth":
        state["birth"] = message.text
        state["step"] = "code"
        await message.answer("Введи кодовое слово:", reply_markup=cancel_inline())
    elif step == "code":
        state["code"] = message.text
        data = load_data()
        app_id = data["counters"]["application_id"] + 1
        data["counters"]["application_id"] = app_id
        app = {
            "id": app_id,
            "user_id": message.from_user.id,
            "username": message.from_user.username or "",
            "chat_key": state["chat_key"],
            "role": state["role"],
            "birth": state["birth"],
            "code": state["code"],
            "status": "pending",
            "admin_feedback": "",
            "created_at": datetime.utcnow().isoformat()
        }
        data["applications"].append(app)
        save_data(data)
        USER_STATE.pop(message.from_user.id, None)
        await message.answer("Заявка отправлена. Ожидай решение администратора.", reply_markup=main_menu())
        await send_admins(
            f"<b>Новая заявка #{app_id}</b>\n"
            f"ID: {app['user_id']}\n"
            f"@{app['username'] or 'no_username'}\n"
            f"Чат: {state['chat_key']}\n"
            f"Роль: {app['role']}\n"
            f"ДР: {app['birth']}\n"
            f"Код: {app['code']}"
        )


@dp.message(F.text == "Мои заявки")
async def my_apps(message: Message):
    data = load_data()
    apps = [a for a in data["applications"] if a["user_id"] == message.from_user.id]
    if not apps:
        await message.answer("У тебя пока нет заявок.", reply_markup=main_menu())
        return
    lines = []
    for a in apps:
        lines.append(f"#{a['id']} — {a['status']} — {a['chat_key']} — {a['role']}")
    await message.answer("\n".join(lines), reply_markup=main_menu())


@dp.message(F.text == "Отменить")
async def cancel_user(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    await message.answer("Текущее действие отменено.", reply_markup=main_menu())


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())