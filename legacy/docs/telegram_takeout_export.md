# Telegram Text Export Through Takeout

Скрипт: [`scripts/export_telegram_chat_text.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/export_telegram_chat_text.py)

Этот скрипт выгружает текст сообщений из одного чата Telegram через MTProto `takeout`.

## Что понадобится

1. Python 3
2. Пакет `telethon`
3. `api_id` и `api_hash` с [my.telegram.org](https://my.telegram.org)

Установка зависимости:

```bash
python3 -m pip install telethon
```

Экспортируй креды в shell:

```bash
export TG_API_ID=123456
export TG_API_HASH=0123456789abcdef0123456789abcdef
```

## Примеры запуска

По username чата или канала:

```bash
python3 scripts/export_telegram_chat_text.py --chat my_channel
```

С выгрузкой в обычный текст:

```bash
python3 scripts/export_telegram_chat_text.py --chat my_channel --format txt
```

С сортировкой от старых к новым:

```bash
python3 scripts/export_telegram_chat_text.py --chat my_channel --reverse
```

С ограничением по количеству сообщений:

```bash
python3 scripts/export_telegram_chat_text.py --chat my_channel --limit 1000
```

С явным файлом сессии:

```bash
python3 scripts/export_telegram_chat_text.py --chat my_channel --session ~/.telegram_takeout.session
```

## Что происходит при первом запуске

- Скрипт попросит логин в Telegram.
- Telegram пришлет код подтверждения.
- Если включен cloud password, Telethon попросит и его.
- После этого рядом появится файл сессии, который лучше хранить приватно.

## Куда пишет результат

По умолчанию:

- `generated/telegram_exports/<chat>.jsonl`

Если выбрать `--format txt`, будет создан `.txt`-файл в той же папке.

## Формат JSONL

Каждая строка содержит один объект сообщения с полями:

- `message_id`
- `date`
- `sender_id`
- `reply_to_msg_id`
- `text`

## Важные ограничения

- По умолчанию скрипт пропускает сообщения без текста.
- Подписи к медиа считаются текстом и сохраняются.
- Если Telegram вернет `TakeoutInitDelayError`, нужно просто подождать указанное число секунд и повторить запуск.
