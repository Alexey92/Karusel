"""
Telegram-бот для инкассации KARUSEL (aiogram).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession

from database import init_db, get_machines, get_last_cashout, save_cashout
from smartvend_api import get_money_from_sales

TOKEN = os.getenv("BOT_TOKEN", "8591247638:AAGMUGdgeWzVYgu7B6rg8toV14sVnzOC0IU")
ALLOWED_USERS = [635009426]  # Aleksis Medina

bot = None
dp = Dispatcher()


async def on_startup():
    await init_db()
    print("[BOT] Бот запущен! Ожидаю команды...")


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "🤖 <b>KARUSEL — Бот инкассации</b>\n\n"
        "Команды:\n"
        "/machines — список автоматов\n"
        "/cashout &lt;сумма&gt; [ID] — сверить инкассацию\n"
        "/help — помощь",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "📖 <b>Как работать:</b>\n\n"
        "1. Снимите деньги с автомата и пересчитайте.\n"
        "2. Отправьте: <code>/cashout 15000 2</code>\n"
        "   (15000 руб., автомат ID 2)\n\n"
        "3. Бот запросит данные SmartVend и сравнит.\n"
        "4. Результат сохранится в БД.\n\n"
        "<i>Пока только чтение — инкассация в SmartVend не создаётся.</i>",
        parse_mode="HTML"
    )


@dp.message(Command("machines"))
async def cmd_machines(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён.")
        return

    machines = await get_machines()
    if not machines:
        await message.answer("📭 Нет автоматов в системе.")
        return

    msg = "🎰 <b>Все автоматы:</b>\n\n"
    for m in machines:
        sv = "✅" if m.get("smartvend_id") else "❌"
        msg += f"• <b>ID {m['id']}</b>: {m['name']} (📍 {m['location_name']}) [SV: {sv}]\n"
    msg += "\nДля инкассации: /cashout &lt;сумма&gt; &lt;ID&gt;"
    await message.answer(msg, parse_mode="HTML")


@dp.message(Command("cashout"))
async def cmd_cashout(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён.")
        return

    args = message.text.split()[1:]  # всё после /cashout

    try:
        amount_rub = int(args[0])
    except (IndexError, ValueError):
        await message.answer(
            "❌ Использование: /cashout <сумма в рублях> [ID автомата]\n"
            "Пример: /cashout 15000 2\n\n"
            "Список автоматов: /machines"
        )
        return

    machine_id = None
    if len(args) > 1:
        try:
            machine_id = int(args[1])
        except ValueError:
            await message.answer("❌ Неверный ID автомата.")
            return

    # Получаем все автоматы с smartvend_id
    all_machines = await get_machines()
    machines_with_sv = [m for m in all_machines if m.get("smartvend_id")]

    if not machines_with_sv:
        await message.answer(
            "⚠️ Нет автоматов, привязанных к SmartVend.\n"
            "Сначала привяжите smartvend_id в админке."
        )
        return

    if machine_id is None:
        if len(machines_with_sv) == 1:
            machine_id = machines_with_sv[0]["id"]
        else:
            msg = "📋 Доступные автоматы (с привязкой к SmartVend):\n\n"
            for m in machines_with_sv:
                msg += f"• ID {m['id']} — {m['name']} (📍 {m['location_name']})\n"
            msg += f"\nИспользуйте: /cashout {amount_rub} <ID>"
            await message.answer(msg)
            return

    machine = next((m for m in machines_with_sv if m["id"] == machine_id), None)
    if not machine:
        await message.answer(f"❌ Автомат ID={machine_id} не найден или не привязан к SmartVend.")
        return

    await message.answer("⏳ Запрашиваю данные из SmartVend...")

    try:
        last = await get_last_cashout(machine_id)
        now = int(datetime.now().timestamp())

        if last and last["created_at"]:
            from_ts = int(last["created_at"].timestamp())
        else:
            from_ts = int((datetime.now() - timedelta(days=30)).timestamp())

        sales_data = await get_money_from_sales(machine["smartvend_id"], from_ts, now)
        api_amount_kop = sales_data["total_money"]
        amount_kop = amount_rub * 100
        diff_kop = amount_kop - api_amount_kop

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

        await save_cashout(
            machine_id=machine_id,
            reported_amount=amount_kop,
            smartvend_amount=api_amount_kop,
            difference=diff_kop,
            smartvend_encashment_id=None
        )

        await message.answer(msg, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка при запросе к SmartVend API:\n{str(e)}")


async def main():
    global bot
    
    # Прокси через BotGate (для России) — абсолютно бесплатно
    session = AiohttpSession(
        proxy="http://botgate.ru:8080"  # если не работает, попробуй tg.lain.la:80
    )
    
    bot = Bot(token=TOKEN, session=session)
    
    await on_startup()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())