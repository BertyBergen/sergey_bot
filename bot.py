import asyncio
import json
import traceback
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, CHAT_IDS, ALLOWED_USERS
from poster import send_to_all

STATE_FILE = Path("state.json")


# ---------- Работа с состоянием ----------
def load_state() -> dict:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("selected_groups", list(CHAT_IDS.keys()))
        return state
    return {
        "message": "Текст не задан",
        "interval_minutes": 0,
        "selected_groups": list(CHAT_IDS.keys()),
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------- Планировщик ----------
scheduler = BackgroundScheduler()
current_job = None


def post_job():
    state = load_state()
    send_to_all(state["message"], targets=state["selected_groups"])


def reschedule(interval_minutes: int):
    global current_job
    if current_job:
        current_job.remove()
        current_job = None
    if interval_minutes > 0:
        current_job = scheduler.add_job(
            post_job,
            "interval",
            minutes=interval_minutes,
            id="autopost",
            replace_existing=True,
        )


# ---------- Меню ----------
def main_menu():
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить текст", callback_data="edit_text")],
        [InlineKeyboardButton("⏱ Интервал", callback_data="interval_menu")],
        [InlineKeyboardButton("👥 Выбрать группы", callback_data="groups_menu")],
        [InlineKeyboardButton("🚀 Опубликовать сейчас", callback_data="post_now")],
    ]
    return InlineKeyboardMarkup(keyboard)


def interval_menu():
    state = load_state()
    cur = state["interval_minutes"]
    label = "Отключено" if cur == 0 else f"{cur} мин"

    keyboard = [
        [
            InlineKeyboardButton("1 мин", callback_data="set_1"),
            InlineKeyboardButton("30 мин", callback_data="set_30"),
            InlineKeyboardButton("1 час", callback_data="set_60"),
        ],
        [
            InlineKeyboardButton("2 часа", callback_data="set_120"),
            InlineKeyboardButton("4 часа", callback_data="set_240"),
        ],
        [InlineKeyboardButton("🚫 Отключить", callback_data="set_0")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ]
    return f"Текущий интервал: {label}", InlineKeyboardMarkup(keyboard)


def groups_menu():
    state = load_state()
    selected = set(state["selected_groups"])

    keyboard = []
    for chat_id, name in CHAT_IDS.items():
        mark = "✅" if chat_id in selected else "⬜"
        keyboard.append([
            InlineKeyboardButton(f"{mark} {name}", callback_data=f"toggle_{chat_id}")
        ])
    keyboard.append([InlineKeyboardButton("✔️ Готово", callback_data="groups_done")])
    return "Выберите группы для публикации:", InlineKeyboardMarkup(keyboard)


def main_text(state: dict) -> str:
    cur = state["interval_minutes"]
    label = "Отключено" if cur == 0 else f"{cur} мин"
    return (
        f"📝 Текущий текст:\n{state['message']}\n\n"
        f"⏱ Интервал: {label}\n"
        f"👥 Групп выбрано: {len(state['selected_groups'])} из {len(CHAT_IDS)}"
    )


# ---------- Проверка доступа ----------
def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


# ---------- Хендлеры ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("Нет доступа.")
        return
    state = load_state()
    await update.message.reply_text(main_text(state), reply_markup=main_menu())


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    print(f"[DEBUG] callback data={query.data!r} from={query.from_user.id}")

    try:
        await query.answer()
    except Exception:
        pass

    if not is_allowed(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return

    data = query.data
    state = load_state()

    if data == "back_main":
        await query.edit_message_text(main_text(state), reply_markup=main_menu())
        return

    if data == "interval_menu":
        text, kb = interval_menu()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("set_"):
        minutes = int(data.split("_")[1])
        state["interval_minutes"] = minutes
        save_state(state)
        reschedule(minutes)
        text, kb = interval_menu()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data == "groups_menu":
        text, kb = groups_menu()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("toggle_"):
        chat_id = int(data.split("_", 1)[1])
        selected = set(state["selected_groups"])
        if chat_id in selected:
            selected.discard(chat_id)
        else:
            selected.add(chat_id)
        state["selected_groups"] = list(selected)
        save_state(state)
        text, kb = groups_menu()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data == "groups_done":
        await query.edit_message_text(main_text(state), reply_markup=main_menu())
        return

    if data == "edit_text":
        ctx.user_data["awaiting_text"] = True
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_edit")]
        ])
        await query.edit_message_text(
            "Пришлите новый текст сообщения одним сообщением.",
            reply_markup=kb,
        )
        return

    if data == "cancel_edit":
        ctx.user_data["awaiting_text"] = False
        await query.edit_message_text(main_text(state), reply_markup=main_menu())
        return

    if data == "post_now":
        print("[DEBUG] post_now: entered")
        if not state["selected_groups"]:
            print("[DEBUG] post_now: no groups selected")
            await query.edit_message_text(
                "⚠️ Не выбрано ни одной группы. Зайдите в «Выбрать группы».",
                reply_markup=main_menu(),
            )
            return
        print(f"[DEBUG] post_now: sending to {state['selected_groups']}")
        result = await asyncio.to_thread(
            send_to_all, state["message"], state["selected_groups"]
        )
        print(f"[DEBUG] post_now: result={result}")
        await query.edit_message_text(
            "✅ Отправлено в выбранные группы.",
            reply_markup=main_menu(),
        )
        return


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not ctx.user_data.get("awaiting_text"):
        return

    new_text = update.message.text
    state = load_state()
    state["message"] = new_text
    save_state(state)
    ctx.user_data["awaiting_text"] = False

    await update.message.reply_text(
        f"✅ Текст обновлён.\n\n{main_text(state)}",
        reply_markup=main_menu(),
    )


# ---------- Обработчик ошибок ----------
async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    print("=== ОШИБКА ===")
    traceback.print_exception(
        type(ctx.error), ctx.error, ctx.error.__traceback__
    )


# ---------- Запуск ----------
def main():
    scheduler.start()
    state = load_state()
    reschedule(state["interval_minutes"])

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    print("Бот запущен.")
    app.run_polling()


if __name__ == "__main__":
    main()