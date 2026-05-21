import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv

from storage import load_config, load_data, next_id, save_data

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flood_bot")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
USER_STATE = {}


def is_admin(user_id: int) -> bool:
    cfg = load_config()
    return user_id == cfg.get("main_admin_id")


def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Подать заявку")
    kb.button(text="Мои заявки")
    kb.button(text="Отменить")
    kb.button(text="Инфо")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def admin_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Заявки")
    kb.button(text="Брони")
    kb.button(text="Статус чатов")
    kb.button(text="Логи")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def cancel_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отменить действие", callback_data="cancel_action")]]
    )


def chat_choice_kb():
    cfg = load_config()
    kb = InlineKeyboardBuilder()
    kb.button(text=cfg["chats"]["chat1"]["title"], callback_data="choose_chat:chat1")
    kb.button(text=cfg["chats"]["chat2"]["title"], callback_data="choose_chat:chat2")
    kb.adjust(1)
    return kb.as_markup()


def apps_kb(app_ids, prefix):
    kb = InlineKeyboardBuilder()
    for app_id in app_ids:
        kb.button(text=f"#{app_id}", callback_data=f"{prefix}:{app_id}")
    kb.adjust(2)
    return kb.as_markup()


async def send_admins(text: str, markup=None):
    cfg = load_config()
    if cfg.get("main_admin_id"):
        await bot.send_message(cfg["main_admin_id"], text, reply_markup=markup)
    if cfg.get("admin_group_id"):
        await bot.send_message(cfg["admin_group_id"], text, reply_markup=markup)


async def get_chat_count(chat_id: int) -> int:
    return await bot.get_chat_member_count(chat_id)


async def is_full(chat_key: str) -> bool:
    cfg = load_config()
    chat = cfg["chats"][chat_key]
    if not chat["chat_id"]:
        return False
    try:
        return (await get_chat_count(chat["chat_id"])) >= chat["member_limit"]
    except Exception as exc:
        logger.warning("Failed to get chat count for %s: %s", chat_key, exc)
        return False


async def create_one_time_link(chat_id: int, title: str, user_id: int) -> str:
    expire_date = datetime.now(timezone.utc) + timedelta(hours=24)
    link = await bot.create_chat_invite_link(
        chat_id=chat_id,
        member_limit=1,
        expire_date=expire_date,
        name=f"{title}-{user_id}-{int(datetime.now().timestamp())}",
    )
    return link.invite_link


@dp.message(CommandStart())
async def start(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    if is_admin(message.from_user.id):
        await message.answer("Админ-панель открыта.", reply_markup=admin_menu())
    else:
        await message.answer("Привет. Выбери действие в меню ниже.", reply_markup=main_menu())


@dp.message(Command("menu"))
async def menu(message: Message):
    if is_admin(message.from_user.id):
        await message.answer("Админ-меню.", reply_markup=admin_menu())
    else:
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
    cfg = load_config()
    chat = cfg["chats"][chat_key]
    if await is_full(chat_key):
        state = USER_STATE.setdefault(call.from_user.id, {})
        state["chat_key"] = chat_key
        state["step"] = "reserve_role"
        await call.message.answer(
            f"{chat['title']} заполнен. Можешь забронировать роль. Введи желаемую роль:",
            reply_markup=cancel_inline(),
        )
        await call.answer()
        return
    USER_STATE[call.from_user.id] = {"chat_key": chat_key, "step": "role"}
    await call.message.answer(
        f"<b>Инфо:</b> {chat['info_url']}\n\nТеперь введи желаемую роль:",
        reply_markup=cancel_inline(),
    )
    await call.answer()


@dp.callback_query(F.data == "cancel_action")
async def cancel_action(call: CallbackQuery):
    USER_STATE.pop(call.from_user.id, None)
    await call.message.answer("Действие отменено.", reply_markup=main_menu())
    await call.answer()


@dp.message(F.text == "Отменить")
async def cancel_user(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    await message.answer("Текущее действие отменено.", reply_markup=main_menu())


@dp.message(F.text == "Мои заявки")
async def my_apps(message: Message):
    data = load_data()
    apps = [a for a in data["applications"] if a["user_id"] == message.from_user.id]
    res = [r for r in data["reservations"] if r["user_id"] == message.from_user.id]
    if not apps and not res:
        await message.answer("У тебя пока нет заявок или броней.", reply_markup=main_menu())
        return
    lines = []
    for a in apps:
        lines.append(f"Заявка #{a['id']} — {a['status']} — {a['chat_key']} — {a['role']}")
    for r in res:
        lines.append(f"Бронь #{r['id']} — {r['status']} — {r['chat_key']} — {r['role']}")
    await message.answer("\n".join(lines), reply_markup=main_menu())


async def add_application(message: Message, state: dict):
    data = load_data()
    app_id = next_id(data, "application_id")
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_link": "",
        "join_confirmed": False,
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
        f"Код: {app['code']}",
        markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_app:{app_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_app:{app_id}"),
                ],
                [InlineKeyboardButton(text="✏️ Отклонить с причиной", callback_data=f"reject_reason:{app_id}")],
            ]
        ),
    )


async def add_reservation(message: Message, state: dict):
    data = load_data()
    rid = next_id(data, "reservation_id")
    reservation = {
        "id": rid,
        "user_id": message.from_user.id,
        "username": message.from_user.username or "",
        "chat_key": state["chat_key"],
        "role": state["role"],
        "status": "reserved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["reservations"].append(reservation)
    save_data(data)
    USER_STATE.pop(message.from_user.id, None)
    await message.answer("Роль забронирована. Мы сообщим, когда появится место.", reply_markup=main_menu())
    await send_admins(
        f"<b>Новая бронь #{rid}</b>\n"
        f"ID: {reservation['user_id']}\n"
        f"@{reservation['username'] or 'no_username'}\n"
        f"Чат: {state['chat_key']}\n"
        f"Роль: {reservation['role']}"
    )


@dp.message(F.text)
async def text_router(message: Message):
    state = USER_STATE.get(message.from_user.id)
    if not state:
        return
    step = state.get("step")
    if step in ("role", "reserve_role"):
        state["role"] = message.text
        state["step"] = "birth" if step == "role" else "reserve_done"
        if step == "reserve_role":
            await add_reservation(message, state)
        else:
            await message.answer("Введи дату рождения (YYYY-MM-DD):", reply_markup=cancel_inline())
    elif step == "birth":
        state["birth"] = message.text
        state["step"] = "code"
        await message.answer("Введи кодовое слово:", reply_markup=cancel_inline())
    elif step == "code":
        state["code"] = message.text
        await add_application(message, state)


@dp.callback_query(F.data.startswith("approve_app:"))
async def approve_app(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    cfg = load_config()
    chat = cfg["chats"][app["chat_key"]]
    if not chat["chat_id"]:
        await call.answer("Не настроен chat_id", show_alert=True)
        return
    link = await create_one_time_link(chat["chat_id"], chat["title"], app["user_id"])
    app["status"] = "approved"
    app["approved_link"] = link
    save_data(data)
    await bot.send_message(
        app["user_id"],
        f"Ваша заявка #{app_id} одобрена.\n\nНажми, чтобы подтвердить вход:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Подтвердить вход", callback_data=f"confirm_join:{app_id}")]]
        ),
    )
    await call.message.answer(f"Заявка #{app_id} одобрена. Ссылка создана.")
    await call.answer()


@dp.callback_query(F.data.startswith("reject_app:"))
async def reject_app(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    app["status"] = "rejected"
    save_data(data)
    await bot.send_message(app["user_id"], f"Ваша заявка #{app_id} отклонена без объяснения.")
    await call.message.answer(f"Заявка #{app_id} отклонена.")
    await call.answer()


@dp.callback_query(F.data.startswith("reject_reason:"))
async def reject_reason(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    USER_STATE[call.from_user.id] = {"step": "reason", "app_id": app_id}
    await call.message.answer("Отправь причину отклонения следующим сообщением.")
    await call.answer()


@dp.message(F.text, F.from_user.id)
async def admin_reason_capture(message: Message):
    state = USER_STATE.get(message.from_user.id)
    if not state or state.get("step") != "reason" or not is_admin(message.from_user.id):
        return
    app_id = state["app_id"]
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        USER_STATE.pop(message.from_user.id, None)
        await message.answer("Заявка не найдена.")
        return
    app["status"] = "rejected"
    app["admin_feedback"] = message.text
    save_data(data)
    await bot.send_message(app["user_id"], f"Ваша заявка #{app_id} отклонена. Причина: {message.text}")
    USER_STATE.pop(message.from_user.id, None)
    await message.answer(f"Причина отправлена по заявке #{app_id}.")


@dp.callback_query(F.data.startswith("confirm_join:"))
async def confirm_join(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app or app["user_id"] != call.from_user.id:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    if not app.get("approved_link"):
        await call.answer("Ссылка не готова", show_alert=True)
        return
    app["join_confirmed"] = True
    save_data(data)
    await bot.send_message(call.from_user.id, f"Вот твоя одноразовая ссылка:\n{app['approved_link']}")
    await send_admins(f"Пользователь {call.from_user.id} подтвердил вход по заявке #{app_id} и получил доступ.")
    await call.message.answer("Вход подтверждён. Админ уведомлён.")
    await call.answer()


@dp.message(F.text == "Заявки")
async def admin_list_apps(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    apps = data["applications"]
    if not apps:
        await message.answer("Заявок нет.", reply_markup=admin_menu())
        return
    text = "\n".join([f"#{a['id']} — {a['status']} — {a['chat_key']} — {a['role']}" for a in apps[-20:]])
    await message.answer(text, reply_markup=admin_menu())


@dp.message(F.text == "Брони")
async def admin_list_res(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    res = data["reservations"]
    if not res:
        await message.answer("Броней нет.", reply_markup=admin_menu())
        return
    text = "\n".join([f"#{r['id']} — {r['status']} — {r['chat_key']} — {r['role']}" for r in res[-20:]])
    await message.answer(text, reply_markup=admin_menu())


@dp.message(F.text == "Статус чатов")
async def admin_chat_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = load_config()
    lines = []
    for key, chat in cfg["chats"].items():
        count = 0
        if chat["chat_id"]:
            try:
                count = await get_chat_count(chat["chat_id"])
            except Exception:
                count = 0
        lines.append(f"{chat['title']}: {count}/{chat['member_limit']}")
    await message.answer("\n".join(lines), reply_markup=admin_menu())


@dp.message(F.text == "Логи")
async def admin_logs(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Логи ведутся в файле bot.log на сервере.", reply_markup=admin_menu())


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
