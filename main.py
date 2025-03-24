import asyncio
import logging
import random
import datetime
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import api_mai
# === Конфигурация ===
TOKEN = api.TOKEN  # Токен телеграмм бота
ADMINS = api.ADMINS  # ID администраторов
CHANNEL_ID = api.CHANNEL_ID # ID или username канала
REQUIRED_APPROVALS = 2  # Количество одобрений для публикации фото

# Папка для хранения фото на сервере
PHOTOS_FOLDER = "photos"
if not os.path.exists(PHOTOS_FOLDER):
    os.makedirs(PHOTOS_FOLDER)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Глобальный счётчик для нумерации фотографий
next_photo_number = 1

# Хранилище для фото, ожидающих модерации.
# pending_photos: { unique_key: { "photo_id": <file_id>,
#                                 "sender_id": <user_id>,
#                                 "origin_chat_id": <chat_id>,
#                                 "origin_message_id": <message_id>,
#                                 "admins": set(),
#                                 "messages": [(admin_id, message_id), ...] } }
pending_photos = {}
# pending_votes: { unique_key: set(admin_id, ...) }
pending_votes = {}

# Глобальный счётчик запланированных фото.
scheduled_count = 0

# Для активного чата админа (устанавливается при нажатии кнопки "💬 Обсудить")
active_chats = {}


# === Обработчик команды /start ===
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Привет! Отправь фото для модерации.")


# === Обработчик команды /chat для администраторов (обсуждение) ===
@dp.message(Command(commands=["chat"]))
async def admin_chat(message: types.Message, command: CommandObject):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔ У вас нет прав для этого действия.")
        return

    admin_id = message.from_user.id
    # Проверяем, есть ли активный чат у администратора
    if admin_id not in active_chats:
        await message.answer("Нет активного чата. Нажмите кнопку '💬 Обсудить' для начала обсуждения.")
        return

    unique_key = active_chats[admin_id]

    if unique_key not in pending_photos:
        await message.answer("Ошибка: фото для текущего чата не найдено.")
        active_chats.pop(admin_id, None)
        return

    if not command.args:
        await message.answer("Введите сообщение после команды /chat")
        return

    chat_text = command.args
    sender = message.from_user.username or str(admin_id)
    formatted_text = f"<b>{sender}:</b> {chat_text}"

    # Отправляем сообщение всем администраторам, кому было отправлено фото
    # (по данным pending_photos[unique_key]["messages"])
    for admin, _ in pending_photos[unique_key]["messages"]:
        if admin == admin_id:
            continue
        try:
            await bot.send_message(chat_id=admin, text=formatted_text)
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения администратору {admin}: {e}")

    await message.answer("Ваше сообщение отправлено в чат по модерации.")


# === Обработчик получения фото для модерации ===
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    global next_photo_number
    # Используем глобальный счётчик для нумерации фотографий
    unique_key = str(next_photo_number)
    next_photo_number += 1

    photo_id = message.photo[-1].file_id
    pending_photos[unique_key] = {
        "photo_id": photo_id,
        "sender_id": message.from_user.id,
        "origin_chat_id": message.chat.id,
        "origin_message_id": message.message_id,
        "admins": set(),
        "messages": []  # сюда запишем кортежи (admin_id, message_id)
    }
    pending_votes[unique_key] = set()

    caption = (
        f"Фото #{unique_key} от @{message.from_user.username or message.from_user.id} на модерации.\n\n"
        "Для обсуждения нажмите кнопку '💬 Обсудить'."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{unique_key}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{unique_key}")
            ],
            [
                InlineKeyboardButton(text="💬 Обсудить", callback_data=f"chat_{unique_key}")
            ]
        ]
    )

    # Рассылаем фото администраторам
    for admin_id in ADMINS:
        try:
            sent_message = await bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=caption,
                reply_markup=keyboard
            )
            pending_photos[unique_key]["messages"].append((admin_id, sent_message.message_id))
        except Exception as e:
            logging.error(f"Ошибка отправки фото администратору {admin_id}: {e}")

    await message.answer("Фото отправлено на модерацию.")


# === Обработчик остальных сообщений ===
@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer("Пожалуйста, отправьте фото или используйте команду /chat.")


# === Обработчик callback-запросов (одобрение, отклонение, обсуждение) ===
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    if len(data_parts) < 2:
        await callback.answer("Ошибка: неверный формат данных.", show_alert=True)
        return

    action, unique_key = data_parts[0], data_parts[1]

    if unique_key not in pending_photos:
        await callback.answer("Ошибка: фото не найдено.", show_alert=True)
        return

    if callback.from_user.id not in ADMINS:
        await callback.answer("⛔ У вас нет прав на это действие.")
        return

    admin_id = callback.from_user.id

    # Если нажата кнопка "💬 Обсудить"
    if action == "chat":
        # Устанавливаем активный чат для данного администратора
        active_chats[admin_id] = unique_key
        instruction = (
            f"Вы начали обсуждение по фото #{unique_key}.\n"
            "Теперь отправляйте сообщения командой: /chat ваше сообщение"
        )
        await callback.message.answer(instruction)
        await callback.answer()
        return

    # Если админ уже голосовал за это фото, не даём повторно голосовать
    if admin_id in pending_votes[unique_key]:
        await callback.answer("Вы уже проголосовали за это фото.")
        return

    pending_votes[unique_key].add(admin_id)

    if action == "approve":
        pending_photos[unique_key]["admins"].add(admin_id)
        if len(pending_photos[unique_key]["admins"]) >= REQUIRED_APPROVALS:
            try:
                file_info = await bot.get_file(pending_photos[unique_key]["photo_id"])
                local_path = os.path.join(PHOTOS_FOLDER, f"{unique_key}.jpg")
                await bot.download_file(file_info.file_path, destination=local_path)
                await callback.answer("Фото одобрено и сохранено на сервере.")

                # Отправляем уведомление отправителю (ответ на исходное сообщение)
                sender_id = pending_photos[unique_key].get("sender_id")
                origin_chat = pending_photos[unique_key].get("origin_chat_id")
                origin_message = pending_photos[unique_key].get("origin_message_id")
                if sender_id and origin_chat and origin_message:
                    try:
                        await bot.send_message(
                            origin_chat,
                            "Ваше фото одобрено!",
                            reply_to_message_id=origin_message
                        )
                    except Exception as e:
                        logging.error(f"Ошибка уведомления отправителя {sender_id}: {e}")

                # Удаляем сообщения модерации у администраторов
                for admin, message_id in pending_photos[unique_key]["messages"]:
                    try:
                        await bot.delete_message(chat_id=admin, message_id=message_id)
                    except Exception as e:
                        logging.error(f"Ошибка удаления сообщения {message_id} в чате {admin}: {e}")

                pending_photos.pop(unique_key)
                pending_votes.pop(unique_key)

                # Убираем активные чаты для данного фото
                for admin in list(active_chats.keys()):
                    if active_chats.get(admin) == unique_key:
                        active_chats.pop(admin, None)

                # Планируем публикацию фото (с рандомным временем в заданном слоте)
                schedule_photo(unique_key)
            except Exception as e:
                await callback.answer(f"Ошибка при обработке фото: {e}", show_alert=True)
        else:
            await callback.answer("Ваш голос учтен. Нужно еще одобрение.")
    elif action == "reject":
        # При отказе уведомление отправителю не отправляем
        for admin, message_id in pending_photos[unique_key]["messages"]:
            try:
                await bot.delete_message(chat_id=admin, message_id=message_id)
            except Exception as e:
                logging.error(f"Ошибка удаления сообщения {message_id} в чате {admin}: {e}")
        pending_photos.pop(unique_key)
        pending_votes.pop(unique_key)
        # Убираем активные чаты, если они были установлены для данного фото
        for admin in list(active_chats.keys()):
            if active_chats.get(admin) == unique_key:
                active_chats.pop(admin, None)
        await callback.answer("Фото отклонено и удалено.")


# === Функция планирования публикации фото согласно схеме (с рандомным смещением) ===
def schedule_photo(unique_key: str):
    """
    Используем глобальный счётчик scheduled_count:
    slot_index = 0 → утро (4-12)
    slot_index = 1 → день (13-17)
    slot_index = 2 → вечер (18-23)
    Если за сутки уже запланировано 3 фото, следующее уйдёт на следующий день.
    """
    global scheduled_count
    day_offset = scheduled_count // 3
    slot_index = scheduled_count % 3
    scheduled_count += 1

    now = datetime.datetime.now()
    target_date = now.date() + datetime.timedelta(days=day_offset)

    if slot_index == 0:
        slot_start_time = datetime.time(4, 0, 0)
        slot_end_time = datetime.time(12, 0, 0)
    elif slot_index == 1:
        slot_start_time = datetime.time(13, 0, 0)
        slot_end_time = datetime.time(17, 0, 0)
    else:
        slot_start_time = datetime.time(18, 0, 0)
        slot_end_time = datetime.time(23, 0, 0)

    slot_start = datetime.datetime.combine(target_date, slot_start_time)
    slot_end = datetime.datetime.combine(target_date, slot_end_time)
    delta_seconds = int((slot_end - slot_start).total_seconds())
    random_offset = random.randint(0, delta_seconds)
    scheduled_time = slot_start + datetime.timedelta(seconds=random_offset)

    delay = (scheduled_time - now).total_seconds()
    if delay < 0:
        delay = 0

    logger.info(f"Фото с ключом {unique_key} запланировано на {scheduled_time} (через {delay} секунд).")
    asyncio.create_task(delayed_send(delay, unique_key))


# === Функция ожидания и отправки запланированного фото ===
async def delayed_send(delay: float, unique_key: str):
    await asyncio.sleep(delay)
    await send_scheduled_photo(unique_key)


# === Функция отправки запланированного фото в канал ===
async def send_scheduled_photo(unique_key: str):
    file_path = os.path.join(PHOTOS_FOLDER, f"{unique_key}.jpg")
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден для публикации.")
        return

    # Создаем экземпляр FSInputFile из пути к файлу
    photo_input = FSInputFile(file_path)
    await bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=photo_input,
    )
    logger.info(f"Опубликовано фото {unique_key} в канале {CHANNEL_ID}.")

    # Удаляем файл с сервера после публикации
    try:
        os.remove(file_path)
        logger.info(f"Файл {file_path} успешно удалён с сервера.")
    except Exception as e:
        logger.error(f"Ошибка удаления файла {file_path}: {e}")


# === Запуск бота ===
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
