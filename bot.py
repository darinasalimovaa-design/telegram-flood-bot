import logging
import os
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv

from storage import load_config, load_data, next_id, save_data

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
_webhook_path_raw = os.getenv("WEBHOOK_PATH", "").strip() or "/webhook"
WEBHOOK_PATH = _webhook_path_raw if _webhook_path_raw.startswith("/") else f"/{_webhook_path_raw}"
WEBHOOK_URL = f"{WEBHOOK_BASE_URL.rstrip('/')}{WEBHOOK_PATH}" if WEBHOOK_BASE_URL else ""
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flood_bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
USER_STATE = {}


# ---------- helpers ----------
def cfg():
    return load_config()


def is_admin(user_id: int) -> bool:
    return user_id == cfg().get("main_admin_id")


def reply_menu(is_admin_user: bool = False):
    kb = ReplyKeyboardBuilder()
    if is_admin_user:
        kb.button(text="Заявки")
        kb.button(text="Брони")
        kb.button(text="Статус чатов")
        kb.button(text="Логи")
        kb.adjust(2, 2)
        return kb.as_markup(resize_keyboard=True)

    kb.button(text="Подать заявку")
    kb.button(text="Мои заявки")
    kb.button(text="Отменить")
    kb.button(text="Инфо")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def cancel_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отменить действие", callback_data="cancel_action")]]
    )


def chat_choice_kb():
    c = cfg()
    kb = InlineKeyboardBuilder()
    kb.button(text=c["chats"]["chat1"]["title"], callback_data="choose_chat:chat1")
    kb.button(text=c["chats"]["chat2"]["title"], callback_data="choose_chat:chat2")
    kb.adjust(1)
    return kb.as_markup()


def admin_app_controls(app_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_app:{app_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_app:{app_id}"),
            ],
            [InlineKeyboardButton(text="✏️ Отклонить с причиной", callback_data=f"reject_reason:{app_id}")],
        ]
    )


def admin_list_kb(items, prefix: str, label: str):
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=f"{label} #{item['id']}", callback_data=f"{prefix}:{item['id']}")
    kb.adjust(1)
    return kb.as_markup()


async def send_admins(text: str, markup=None):
    c = cfg()
    targets = [c.get("main_admin_id"), c.get("admin_group_id")]
    for chat_id in targets:
        if chat_id:
            try:
                await bot.send_message(chat_id, text, reply_markup=markup)
            except Exception as exc:
                logger.warning("Failed to send admin message to %s: %s", chat_id, exc)


async def get_chat_count(chat_id: int) -> int:
    return await bot.get_chat_member_count(chat_id)


async def is_full(chat_key: str) -> bool:
    chat = cfg()["chats"][chat_key]
    if not chat["chat_id"]:
        return False
    try:
        return (await get_chat_count(chat["chat_id"])) >= chat["member_limit"]
    except Exception as exc:
        logger.warning("Failed to get chat count for %s: %s", chat_key, exc)
        return False


async def create_one_time_link(chat_id: int, title: str, user_id: int) -> str:
    expire_date = datetime.now(timezone.utc) + timedelta(hours=24)
    invite = await bot.create_chat_invite_link(
        chat_id=chat_id,
        member_limit=1,
        expire_date=expire_date,
        name=f"{title}-{user_id}-{int(datetime.now().timestamp())}",
    )
    return invite.invite_link


async def find_application(app_id: int):
    data = load_data()
    return data, next((a for a in data["applications"] if a["id"] == app_id), None)


async def find_reservation(res_id: int):
    data = load_data()
    return data, next((r for r in data["reservations"] if r["id"] == res_id), None)


async def send_application_card(target_chat_id: int, app: dict, with_controls: bool = True):
    text = (
        f"📩 <b>Новая заявка #{app['id']}</b>\n"
        f"<b>ID:</b> <code>{app['user_id']}</code>\n"
        f"<b>Username:</b> @{escape(app['username']) if app['username'] else 'no_username'}\n"
        f"<b>Чат:</b> {escape(app['chat_key'])}\n"
        f"<b>Роль:</b> {escape(app['role'])}\n"
        f"<b>ДР:</b> {escape(app['birth'])}\n"
        f"<b>Код:</b> {escape(app['code'])}\n"
        f"<b>Статус:</b> {escape(app['status'])}"
    )
    await bot.send_message(target_chat_id, text, reply_markup=admin_app_controls(app["id"]) if with_controls else None)


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

    await message.answer(
        "✅ <b>Заявка отправлена</b>\n"
        "Теперь ожидай решение администратора.",
        reply_markup=reply_menu(False),
    )

    await send_admins(
        "📩 <b>Новая заявка</b>\n"
        f"<b>ID:</b> <code>{app['user_id']}</code>\n"
        f"<b>Username:</b> @{escape(app['username']) if app['username'] else 'no_username'}\n"
        f"<b>Чат:</b> {escape(state['chat_key'])}\n"
        f"<b>Роль:</b> {escape(app['role'])}\n"
        f"<b>ДР:</b> {escape(app['birth'])}\n"
        f"<b>Код:</b> {escape(app['code'])}\n"
        f"<b>Заявка #</b>{app_id}",
        markup=admin_app_controls(app_id),
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

    await message.answer(
        "📌 <b>Роль забронирована</b>\n"
        "Мы сообщим, когда в чате появится место.",
        reply_markup=reply_menu(False),
    )
    await send_admins(
        "📌 <b>Новая бронь</b>\n"
        f"<b>ID:</b> <code>{reservation['user_id']}</code>\n"
        f"<b>Username:</b> @{escape(reservation['username']) if reservation['username'] else 'no_username'}\n"
        f"<b>Чат:</b> {escape(state['chat_key'])}\n"
        f"<b>Роль:</b> {escape(reservation['role'])}\n"
        f"<b>Бронь #</b>{rid}",
    )


def applications_text(apps):
    return "\n".join([f"#{a['id']} — {a['status']} — {a['chat_key']} — {a['role']}" for a in apps])


def reservations_text(res):
    return "\n".join([f"#{r['id']} — {r['status']} — {r['chat_key']} — {r['role']}" for r in res])


# ---------- public flow ----------
@dp.message(CommandStart())
async def start(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    await message.answer(
        "👋 <b>Привет!</b>\n"
        "Это бот для подачи заявки на вход в один из двух чатов.\n"
        "Выбери действие в меню ниже.",
        reply_markup=reply_menu(is_admin(message.from_user.id)),
    )


@dp.message(Command("menu"))
async def menu(message: Message):
    await message.answer("📋 <b>Меню открыто</b>", reply_markup=reply_menu(is_admin(message.from_user.id)))


@dp.message(F.text == "Инфо")
async def info(message: Message):
    c = cfg()
    text = (
        f"<b>{escape(c['chats']['chat1']['title'])}</b>\n"
        f"Инфо: {escape(c['chats']['chat1']['info_url'])}\n\n"
        f"<b>{escape(c['chats']['chat2']['title'])}</b>\n"
        f"Инфо: {escape(c['chats']['chat2']['info_url'])}"
    )
    await message.answer(text, reply_markup=reply_menu(False))


@dp.message(F.text == "Подать заявку")
async def apply(message: Message):
    await message.answer("Выбери чат, в который хочешь попасть:", reply_markup=chat_choice_kb())


@dp.callback_query(F.data.startswith("choose_chat:"))
async def choose_chat(call: CallbackQuery):
    chat_key = call.data.split(":", 1)[1]
    c = cfg()
    chat = c["chats"][chat_key]

    if await is_full(chat_key):
        USER_STATE[call.from_user.id] = {"chat_key": chat_key, "step": "reserve_role"}
        await call.message.answer(
            f"⚠️ <b>{escape(chat['title'])}</b> сейчас заполнен.\n"
            f"Если хочешь, можешь забронировать роль.\n\n"
            f"Сначала изучи инфо: {escape(chat['info_url'])}\n\n"
            f"Введи желаемую роль:",
            reply_markup=cancel_inline(),
        )
        await call.answer()
        return

    USER_STATE[call.from_user.id] = {"chat_key": chat_key, "step": "role"}
    await call.message.answer(
        f"📌 <b>Сначала ознакомься с инфо:</b>\n{escape(chat['info_url'])}\n\n"
        f"Теперь введи желаемую роль:",
        reply_markup=cancel_inline(),
    )
    await call.answer()


@dp.callback_query(F.data == "cancel_action")
async def cancel_action(call: CallbackQuery):
    USER_STATE.pop(call.from_user.id, None)
    await call.message.answer("❎ <b>Действие отменено</b>", reply_markup=reply_menu(is_admin(call.from_user.id)))
    await call.answer()


@dp.message(F.text == "Отменить")
async def cancel_user(message: Message):
    USER_STATE.pop(message.from_user.id, None)
    await message.answer("❎ <b>Текущее действие отменено</b>", reply_markup=reply_menu(is_admin(message.from_user.id)))


@dp.message(F.text == "Мои заявки")
async def my_apps(message: Message):
    data = load_data()
    apps = [a for a in data["applications"] if a["user_id"] == message.from_user.id]
    res = [r for r in data["reservations"] if r["user_id"] == message.from_user.id]
    if not apps and not res:
        await message.answer("У тебя пока нет заявок или броней.", reply_markup=reply_menu(False))
        return

    parts = []
    for a in apps:
        parts.append(f"Заявка <b>#{a['id']}</b> — <b>{escape(a['status'])}</b> — {escape(a['chat_key'])} — {escape(a['role'])}")
    for r in res:
        parts.append(f"Бронь <b>#{r['id']}</b> — <b>{escape(r['status'])}</b> — {escape(r['chat_key'])} — {escape(r['role'])}")
    await message.answer("\n".join(parts), reply_markup=reply_menu(False))


@dp.message(F.text)
async def text_router(message: Message):
    state = USER_STATE.get(message.from_user.id)
    if not state:
        return

    step = state.get("step")
    if step in ("role", "reserve_role"):
        state["role"] = message.text.strip()
        if step == "reserve_role":
            await add_reservation(message, state)
        else:
            state["step"] = "birth"
            await message.answer("Введи дату рождения в формате <code>YYYY-MM-DD</code>:", reply_markup=cancel_inline())
        return

    if step == "birth":
        state["birth"] = message.text.strip()
        state["step"] = "code"
        await message.answer("Введи кодовое слово:", reply_markup=cancel_inline())
        return

    if step == "code":
        state["code"] = message.text.strip()
        await add_application(message, state)
        return

    if step == "reason" and is_admin(message.from_user.id):
        app_id = state.get("app_id")
        data = load_data()
        app = next((a for a in data["applications"] if a["id"] == app_id), None)
        if not app:
            USER_STATE.pop(message.from_user.id, None)
            await message.answer("Заявка не найдена.")
            return
        app["status"] = "rejected"
        app["admin_feedback"] = message.text.strip()
        save_data(data)
        await bot.send_message(app["user_id"], f"❌ <b>Ваша заявка #{app_id} отклонена</b>\n\nПричина: {escape(message.text.strip())}")
        USER_STATE.pop(message.from_user.id, None)
        await message.answer(f"Причина отправлена по заявке #{app_id}.")
        return


# ---------- admin actions ----------
@dp.callback_query(F.data.startswith("approve_app:"))
async def approve_app(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    chat = cfg()["chats"][app["chat_key"]]
    if not chat["chat_id"]:
        await call.answer("Не настроен chat_id в config.json", show_alert=True)
        return

    try:
        link = await create_one_time_link(chat["chat_id"], chat["title"], app["user_id"])
    except Exception as exc:
        logger.exception("Failed to create invite link: %s", exc)
        await call.answer("Не удалось создать ссылку", show_alert=True)
        return

    app["status"] = "approved"
    app["approved_link"] = link
    save_data(data)

    await bot.send_message(
        app["user_id"],
        "✅ <b>Ваша заявка одобрена</b>\n\n"
        "Нажми кнопку ниже, чтобы подтвердить вход.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Подтвердить вход", callback_data=f"confirm_join:{app_id}")]]
        ),
    )
    await call.message.answer(f"✅ Заявка #{app_id} одобрена. Одноразовая ссылка создана.")
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
    await bot.send_message(app["user_id"], f"❌ <b>Ваша заявка #{app_id} отклонена</b>\n\nБез объяснения.")
    await call.message.answer(f"❌ Заявка #{app_id} отклонена без объяснения.")
    await call.answer()


@dp.callback_query(F.data.startswith("reject_reason:"))
async def reject_reason(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    USER_STATE[call.from_user.id] = {"step": "reason", "app_id": app_id}
    await call.message.answer("Напиши причину отклонения следующим сообщением.")
    await call.answer()


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

    await bot.send_message(
        call.from_user.id,
        f"🔗 <b>Вот твоя одноразовая ссылка</b>\n{app['approved_link']}\n\n"
        f"После входа админ получит уведомление.",
    )
    await send_admins(f"✅ Пользователь <code>{call.from_user.id}</code> подтвердил вход по заявке #{app_id} и получил доступ.")
    await call.message.answer("✅ Вход подтверждён. Админ уведомлён.")
    await call.answer()


# ---------- admin panel ----------
@dp.message(F.text == "Заявки")
async def admin_list_apps(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    apps = data["applications"]
    pending = [a for a in apps if a["status"] == "pending"]
    if not apps:
        await message.answer("Заявок нет.", reply_markup=reply_menu(True))
        return

    await message.answer(
        f"📥 <b>Всего заявок:</b> {len(apps)}\n<b>Ожидают:</b> {len(pending)}",
        reply_markup=reply_menu(True),
    )

    if pending:
        await message.answer(
            "<b>Ожидающие заявки:</b>\n\n" + applications_text(pending[-20:]),
            reply_markup=admin_list_kb(pending[-10:], "app", "Заявка"),
        )


@dp.message(F.text == "Брони")
async def admin_list_res(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    res = data["reservations"]
    if not res:
        await message.answer("Броней нет.", reply_markup=reply_menu(True))
        return
    await message.answer(
        f"📌 <b>Всего броней:</b> {len(res)}",
        reply_markup=reply_menu(True),
    )
    await message.answer(
        "<b>Список броней:</b>\n\n" + reservations_text(res[-20:]),
        reply_markup=admin_list_kb(res[-10:], "res", "Бронь"),
    )


@dp.message(F.text == "Статус чатов")
async def admin_chat_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    c = cfg()
    lines = []
    for key, chat in c["chats"].items():
        count = 0
        if chat["chat_id"]:
            try:
                count = await get_chat_count(chat["chat_id"])
            except Exception:
                count = 0
        lines.append(f"<b>{escape(chat['title'])}</b>: {count}/{chat['member_limit']}")
    await message.answer("\n".join(lines), reply_markup=reply_menu(True))


@dp.message(F.text == "Логи")
async def admin_logs(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📝 Логи пишутся в <code>bot.log</code> на сервере.", reply_markup=reply_menu(True))


# ---------- admin commands in group and private ----------
@dp.message(Command("applications"))
async def cmd_applications(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    apps = data["applications"]
    if not apps:
        await message.answer("Заявок нет.")
        return
    pending = [a for a in apps if a["status"] == "pending"]
    await message.answer(
        f"📥 Всего заявок: {len(apps)}\nОжидают: {len(pending)}",
    )
    if pending:
        await message.answer("Ожидающие заявки:\n\n" + applications_text(pending[-30:]), reply_markup=admin_list_kb(pending[-12:], "app", "Заявка"))


@dp.message(Command("reservations"))
async def cmd_reservations(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    res = data["reservations"]
    if not res:
        await message.answer("Броней нет.")
        return
    await message.answer(f"📌 Всего броней: {len(res)}")
    await message.answer("Список броней:\n\n" + reservations_text(res[-30:]), reply_markup=admin_list_kb(res[-12:], "res", "Бронь"))


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    await admin_chat_status(message)


@dp.message(Command("pending"))
async def cmd_pending(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    pending = [a for a in data["applications"] if a["status"] == "pending"]
    if not pending:
        await message.answer("Ожидающих заявок нет.")
        return
    await message.answer("Ожидающие заявки:\n\n" + applications_text(pending[-30:]), reply_markup=admin_list_kb(pending[-12:], "app", "Заявка"))


@dp.callback_query(F.data.startswith("app:"))
async def app_quick_view(call: CallbackQuery):
    app_id = int(call.data.split(":", 1)[1])
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    await call.message.answer(
        f"<b>Заявка #{app['id']}</b>\n"
        f"<b>ID:</b> <code>{app['user_id']}</code>\n"
        f"<b>Username:</b> @{escape(app['username']) if app['username'] else 'no_username'}\n"
        f"<b>Чат:</b> {escape(app['chat_key'])}\n"
        f"<b>Роль:</b> {escape(app['role'])}\n"
        f"<b>ДР:</b> {escape(app['birth'])}\n"
        f"<b>Код:</b> {escape(app['code'])}\n"
        f"<b>Статус:</b> {escape(app['status'])}\n"
        f"<b>Причина отказа:</b> {escape(app['admin_feedback'] or '-')}",
        reply_markup=admin_app_controls(app_id),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("res:"))
async def res_quick_view(call: CallbackQuery):
    res_id = int(call.data.split(":", 1)[1])
    data = load_data()
    res = next((r for r in data["reservations"] if r["id"] == res_id), None)
    if not res:
        await call.answer("Бронь не найдена", show_alert=True)
        return
    await call.message.answer(
        f"<b>Бронь #{res['id']}</b>\n"
        f"<b>ID:</b> <code>{res['user_id']}</code>\n"
        f"<b>Username:</b> @{escape(res['username']) if res['username'] else 'no_username'}\n"
        f"<b>Чат:</b> {escape(res['chat_key'])}\n"
        f"<b>Роль:</b> {escape(res['role'])}\n"
        f"<b>Статус:</b> {escape(res['status'])}",
    )
    await call.answer()


async def process_update(update_data: dict):
    update = Update.model_validate(update_data)
    await dp.feed_update(bot, update)


async def configure_webhook():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET or None,
            drop_pending_updates=False,
        )
        logger.info("Webhook is set: %s", WEBHOOK_URL)
    else:
        logger.info("WEBHOOK_BASE_URL is not set. Webhook registration skipped.")


async def shutdown():
    await bot.session.close()
