"""
Telegram-бот для инкассации KARUSEL.
Пока только чтение из SmartVend API, без создания инкассаций.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Добавляем путь к проекту для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from database import get_pool, init_db, get_machines, get_last_cashout, save_cashout
from smartvend_api import get_money_from_sales

TOKEN = os.getenv("BOT_TOKEN", "8591247638:AAGMUGdgeWzVYgu7B6rg8toV14sVnzOC0IU")

# Кому разрешён доступ
ALLOWED_USERS = [635009426]  # Aleksis Medina


async def on_startup():
    """Инициализация при старте."""
    await init_db()


async def get_all_machines() -> list:
    """Получить все автоматы из БД."""
    return await get_machines()


async def cashout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /cashout <сумма> [ID автомата]"""
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    # Парсим сумму
    try:
        amount_rub = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Использование: /cashout <сумма в рублях> [ID автомата]\n"
            "Пример: /cashout 15000 2\n\n"
            "Список автоматов: /machines"
        )
        return

    # Парсим ID автомата (опционально)
    machine_id = None
    if len(context.args) > 1:
        try:
            machine_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Неверный ID автомата.")
            return

    # Получаем все автоматы
    all_machines = await get_all_machines()
    machines_with_smartvend = [m for m in all_machines if m.get("smartvend_id")]

    if not machines_with_smartvend:
        await update.message.reply_text(
            "⚠️ Нет автоматов, привязанных к SmartVend.\n"
            "Сначала привяжите smartvend_id в админке."
        )
        return

    # Если автомат не указан
    if machine_id is None:
        if len(machines_with_smartvend) == 1:
            machine_id = machines_with_smartvend[0]["id"]
        else:
            msg = "📋 Доступные автоматы (с привязкой к SmartVend):\n\n"
            for m in machines_with_smartvend:
                msg += f"• ID {m['id']} — {m['name']} (📍 {m['location_name']})\n"
            msg += f"\nИспользуйте: /cashout {amount_rub} <ID>"
            await update.message.reply_text(msg)
            return

    # Ищем автомат
    machine = next((m for m in machines_with_smartvend if m["id"] == machine_id), None)
    if not machine:
        await update.message.reply_text(
            f"❌ Автомат ID={machine_id} не найден или не привязан к SmartVend."
        )
        return

    # Запрашиваем данные из SmartVend
    await update.message.reply_text("⏳ Запрашиваю данные из SmartVend...")

    try:
        # Период: от последней инкассации до сейчас
        last = await get_last_cashout(machine_id)
        now = int(datetime.now().timestamp())

        if last and last["created_at"]:
            from_ts = int(last["created_at"].timestamp())
        else:
            # Если не было инкассаций — последние 30 дней
            from_ts = int((datetime.now() - timedelta(days=30)).timestamp())

        sales_data = await get_money_from_sales(machine["smartvend_id"], from_ts, now)
        api_amount_kop = sales_data["total_money"]  # в копейках
        amount_kop = amount_rub * 100
        diff_kop = amount_kop - api_amount_kop

        # Формируем ответ
        diff_rub = abs(diff_kop) // 100
        diff_kop_rem = abs(diff_kop) % 100

        msg = (
            f"📊 <b>Результат инкассации</b>\n"
            f"Автомат: <b>{machine['name']}</b> (ID {machine_id})\n"
            f"Адрес: 📍 {machine['location_name']}\n"
            f"SmartVend ID: <code>{machine['smartvend_id'][:12]}...</code>\n\n"
            f"💰 Заявлено: <b>{amount_rub} руб.</b>\n"
            f"💳 По API: <b>{api_amount_kop // 100} руб. {api_amount_kop % 100} коп.</b>\n"
            f"📈 Продаж за период: <b>{sales_data['total_sales']}</b>\n\n"
        )

        if diff_kop == 0:
            msg += "✅ Суммы совпадают!"
        elif abs(diff_kop) < 100:
            msg += f"✅ Расхождение: {diff_kop} коп. (в пределах погрешности)"
        elif diff_kop > 0:
            msg += f"⚠️ ИЗЛИШЕК: +{diff_rub} руб. {diff_kop_rem} коп."
        else:
            msg += f"🔴 НЕДОСТАЧА: -{diff_rub} руб. {diff_kop_rem} коп."

        # Сохраняем в БД
        await save_cashout(
            machine_id=machine_id,
            reported_amount=amount_kop,
            smartvend_amount=api_amount_kop,
            difference=diff_kop,
            smartvend_encashment_id=None  # Пока не создаём в SmartVend
        )

        await update.message.reply_text(msg, parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запросе к SmartVend API:\n{str(e)}")


async def machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список автоматов."""
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    all_machines = await get_all_machines()

    if not all_machines:
        await update.message.reply_text("📭 Нет автоматов в системе.")
        return

    msg = "🎰 <b>Все автоматы:</b>\n\n"
    for m in all_machines:
        sv = "✅" if m.get("smartvend_id") else "❌"
        msg += f"• <b>ID {m['id']}</b>: {m['name']} (📍 {m['location_name']}) [SV: {sv}]\n"

    msg += "\nДля инкассации: /cashout &lt;сумма&gt; &lt;ID&gt;"
    await update.message.reply_text(msg, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    await update.message.reply_text(
        "🤖 <b>KARUSEL — Бот инкассации</b>\n\n"
        "Команды:\n"
        "/machines — список автоматов\n"
        "/cashout &lt;сумма&gt; [ID] — сверить инкассацию\n"
        "/help — помощь",
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь."""
    await update.message.reply_text(
        "📖 <b>Как работать:</b>\n\n"
        "1. Снимите деньги с автомата и пересчитайте.\n"
        "2. Отправьте: <code>/cashout 15000 2</code>\n"
        "   (15000 руб., автомат ID 2)\n\n"
        "3. Бот запросит данные SmartVend и сравнит.\n"
        "4. Результат сохранится в БД.\n\n"
        "<i>Пока только чтение — инкассация в SmartVend не создаётся.</i>",
        parse_mode="HTML"
    )


def main():
    """Запуск бота."""
    # Для России и стран с блокировкой Telegram — прокси
    # Если SOCKS5:
    # proxy = "socks5://138.16.29.205:64143"
    # Если HTTP-прокси:
    proxy = "http://MrLhU7twz:WB4ZJgbrb@154.213.7.9:64876"
    
    app = Application.builder().token(TOKEN).build()

    # Инициализация БД при старте
    app.post_init = on_startup

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("machines", machines))
    app.add_handler(CommandHandler("cashout", cashout))

    print("[BOT] Бот запущен! Ожидаю команды...")
    app.run_polling()


if __name__ == "__main__":
    main()