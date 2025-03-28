# Telegram-Photo-Moderation-Bot

Проект представляет собой бота для Telegram, который позволяет модераторам оценивать отправленные пользователями фотографии, вести обсуждение и планировать публикацию фото в канал с использованием случайного времени в заданном временном интервале.

**Основные возможности
Модерация фото:**

Пользователи отправляют фото, а бот пересылает их администраторам для одобрения или отклонения.

**Система голосования:**

Фотография публикуется в канал только после получения заданного количества одобрений (REQUIRED_APPROVALS).

**Рандомное планирование публикации:**

После одобрения фото публикуется в канале в случайное время, выбранное в пределах одного из трёх временных слотов (утро, день или вечер). Если за сутки уже запланировано 3 фото, следующие будут отложены на следующий день.

**Встроенный чат для администраторов:**

Администраторы могут вести обсуждение по фото без указания ключа — достаточно активировать чат нажатием кнопки «💬 Обсудить» и отправлять сообщения командой /chat ваше сообщение.

**Очистка сервера:**

После публикации фото файл удаляется с сервера.

**Установка и запуск
Предварительные требования**

•Python 3.8 или выше

•Пакетный менеджер pip

**Установка зависимостей**
Склонируйте репозиторий и установите зависимости:

```
git clone https://github.com/your_username/telegram-photo-moderation-bot.git
cd telegram-photo-moderation-bot
pip install -r requirements.txt
```
**Настройка:**

1. Откройте файл конфигурации api.py и замените значение переменной TOKEN на токен вашего бота.

2. Укажите ID администраторов в переменной ADMINS.

3. Установите username или ID канала, в который будут публиковаться фото, в переменной CHANNEL_ID.

При необходимости измените количество одобрений для публикации фото, значение переменной REQUIRED_APPROVALS.

**Запуск бота**

Запустите бота с помощью Python:
```
python main.py
```
Бот начнёт принимать сообщения и фото, пересылая их администраторам для модерации.

**Структура проекта:**

• main.py – основной файл бота, содержащий логику модерации, чат для администраторов и планирование публикаций.

• requirements.txt – список зависимостей проекта.

• photos/ – папка для временного хранения фото, ожидающих публикации.
