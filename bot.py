import json
import os
from pathlib import Path

import requests
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
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"message": "Текст не задан", "interval_minutes": 0}


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
    send_to_all(state["message"])


def reschedule(interval_minutes: int):
    """Пересоздаёт задачу в планировщике под новый интервал."""
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


# ---------- Проверка доступа ----------
def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


# ---------- Хендлеры ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("Нет доступа.")
        return
    state = load_state()
    cur = state["interval_minutes"]
    label = "Отключено" if cur == 0 else f"{cur} мин"
    text = (
        f"📝 Текущий текст:\n{state['message']}\n\n"
        f"⏱ Интервал: {label}"
    )
    await update.message.reply_text(text, reply_markup=main_menu())


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_allowed(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return

    data = query.data
    state = load_state()

    if data == "back_main":
        cur = state["interval_minutes"]
        label = "Отключено" if cur == 0 else f"{cur} мин"
        text = (
            f"📝 Текущий текст:\n{state['message']}\n\n"
            f"⏱ Интервал: {label}"
        )
        await query.edit_message_text(text, reply_markup=main_menu())
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

    if data == "edit_text":
        ctx.user_data["awaiting_text"] = True
        await query.edit_message_text(
            "Пришлите новый текст сообщения одним сообщением."
        )
        return

    if data == "post_now":
        send_to_all(state["message"])
        await query.edit_message_text(
            "✅ Отправлено во все группы.",
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

    cur = state["interval_minutes"]
    label = "Отключено" if cur == 0 else f"{cur} мин"
    await update.message.reply_text(
        f"✅ Текст обновлён.\n\n📝 {new_text}\n\n⏱ Интервал: {label}",
        reply_markup=main_menu(),
    )


# ---------- Запуск ----------
def main():
    scheduler.start()
    # восстанавливаем интервал из файла при старте
    state = load_state()
    reschedule(state["interval_minutes"])

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Бот запущен.")
    app.run_polling()


if __name__ == "__main__":
    main()