# main.py
import os
import asyncio
from decimal import Decimal
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

from db import init_db, add_user, add_money, get_last_money, get_all_user_ids

from dotenv import load_dotenv

load_dotenv()
API_URL = "https://openexchangerates.org/api/latest.json"
APP_ID = "a2da56f7ba06492393dcfcba9a7dc300"  # перемести в переменные окружения в реальном проекте


BOT_TOKEN = os.getenv("TG_TOKEN") or "REPLACE_WITH_YOUR_TOKEN"  # убери токен из кода, используй env

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()

# кнопка
keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Обновить")]],
    resize_keyboard=True
)

@router.message(Command("start"))
async def cmd_start(message: Message):
    added = await add_user(message.from_user.id)
    if added:
        await message.answer("Ты добавлен в базу и будешь получать обновления.", reply_markup=keyboard)
    else:
        await message.answer("Ты уже есть в базе.", reply_markup=keyboard)

@router.message(F.text == "Обновить")
async def handle_manual_refresh(message: Message):
    last = await get_last_money()
    if last:
        text = f"USD→RUB: {last.usd_to_rub}\nUSD→KZT: {last.usd_to_kz}\nRUB→KZT: {last.rub_kz}\nВремя (UTC): {last.time}"
    else:
        text = "Нет данных."
    await message.answer(text)

# РАССЫЛКА (пример, доступ только владельцу)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
@router.message(Command("send"))
async def broadcast(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("Нет прав.")
        return
    # /send Текст...
    args = message.get_args()
    if not args:
        await message.answer("Укажи текст: /send Привет всем")
        return
    users = await get_all_user_ids()
    counter = 0
    for uid in users:
        try:
            await bot.send_message(uid, args)
            counter += 1
        except Exception as e:
            print("send error", uid, e)
    await message.answer(f"Отправлено {counter} из {len(users)}")

dp.include_router(router)

# в main.py
ALERT_THRESHOLD = Decimal("0.05")  # 5% разницы

async def check_and_alert(new_usd_rub, new_usd_kz, new_rub_kz):
    last = await get_last_money()
    if not last:
        return
    def diff(old, new):
        return abs(new - old) / old if old != 0 else Decimal("0")
    changes = []
    if diff(last.usd_to_rub, new_usd_rub) >= ALERT_THRESHOLD:
        changes.append(f"USD→RUB изменился на {diff(last.usd_to_rub, new_usd_rub) * 100:.2f}%")
    if diff(last.usd_to_kz, new_usd_kz) >= ALERT_THRESHOLD:
        changes.append(f"USD→KZT изменился на {diff(last.usd_to_kz, new_usd_kz) * 100:.2f}%")
    if diff(last.rub_kz, new_rub_kz) >= ALERT_THRESHOLD:
        changes.append(f"RUB→KZT изменился на {diff(last.rub_kz, new_rub_kz) * 100:.2f}%")
    if changes:
        users = await get_all_user_ids()
        for uid in users:
            try:
                await bot.send_message(uid, "⚠ Значительное изменение курса:\n" + "\n".join(changes))
            except Exception as e:
                print("alert send error", uid, e)

async def fetch_rates_and_store(session_http: aiohttp.ClientSession):
    params = {"app_id": APP_ID}
    async with session_http.get(API_URL, params=params, timeout=30) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"API error {resp.status}: {text}")
        data = await resp.json()

    usd_rub = Decimal(str(data["rates"]["RUB"]))
    usd_kz = Decimal(str(data["rates"]["KZT"]))
    rub_kz = (usd_kz / usd_rub).quantize(Decimal("0.00000001"))

    # Сначала проверка изменений
    await check_and_alert(usd_rub, usd_kz, rub_kz)

    # Потом сохранение
    await add_money(usd_rub, usd_kz, rub_kz)
    return usd_rub, usd_kz, rub_kz

# Фоновая задача: fetch rates и save
async def fetch_rates_and_store(session_http: aiohttp.ClientSession):
    params = {"app_id": APP_ID}
    async with session_http.get(API_URL, params=params, timeout=30) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"API error {resp.status}: {text}")
        data = await resp.json()
    # безопасно через Decimal
    usd_rub = Decimal(str(data["rates"]["RUB"]))
    usd_kz = Decimal(str(data["rates"]["KZT"]))
    rub_kz = (usd_kz / usd_rub).quantize(Decimal("0.00000001"))  # точность
    await add_money(usd_rub, usd_kz, rub_kz)
    return usd_rub, usd_kz, rub_kz

async def rates_worker(stop_event: asyncio.Event):
    # делаем один запрос сразу после старта, затем раз в час
    async with aiohttp.ClientSession() as http:
        while not stop_event.is_set():
            try:
                usd_rub, usd_kz, rub_kz = await fetch_rates_and_store(http)
                print(f"[{datetime.now(timezone.utc).isoformat()}] saved: {usd_rub} {usd_kz} {rub_kz}")
            except Exception as e:
                print("Rates fetch/store error:", e)
            # ждем до следующего полного часа (опционально) или просто 3600
            now = datetime.now(timezone.utc)
            # секунд до следующего часа:
            secs = 3600 - (now.minute * 60 + now.second)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=secs)
            except asyncio.TimeoutError:
                pass  # ничего не произошло, просто ждем дальше

async def main():
    # инициализация БД
    await init_db()

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(rates_worker(stop_event))

    try:
        await dp.start_polling(bot)
    finally:
        # остановка фоновой задачи
        stop_event.set()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

