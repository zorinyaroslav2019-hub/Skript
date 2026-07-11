import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel

# ============ КОНФИГУРАЦИЯ И НАСТРОЙКИ ============
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

# Railway берет сессию из переменных окружения (TELEGRAM_SESSION).
# Если запускаете локально без переменной — будет использоваться файл 'composite_session'.
SESSION_STRING = os.environ.get("TELEGRAM_SESSION")

# Инициализируем один клиент
client = TelegramClient(StringSession(SESSION_STRING) if SESSION_STRING else 'composite_session', API_ID, API_HASH)

# ============ НАСТРОЙКИ ЧАТОВ И КАНАЛОВ ============

# Чат для ловли чеков и ФК
GMINES_CHAT = 'gmineschat'
# Бот для активации чеков
TARGET_BOT = 'gminesbot'

# Конфигурация пар канал -> чат обсуждения для комментариев "ФК"
# Добавляйте/удаляйте пары здесь. @username канала и его чата обсуждения.
CHANNEL_COMMENT_CONFIGS = [
    {'source': 'NEVGMP', 'target': 'NEVAPIK'},
    {'source': 'simixGMP', 'target': 'chat_simixa'},
    {'source': 'rozdaci', 'target': 'rozdaci_p'}
]

# Список всех чатов, которые бот будет слушать для комментариев ФК
# (создается автоматически из CHANNEL_COMMENT_CONFIGS)
COMMENT_TARGET_CHATS = [config['target'] for config in CHANNEL_COMMENT_CONFIGS]

# Словарь для хранения resolved ID каналов (source_channel_id -> source_channel_username)
# Используется для быстрой проверки, из какого канала пришло пересланное сообщение
SOURCE_CHANNEL_IDS_MAP = {} 

# ============ ОБРАБОТЧИК 1: GMINESCHAT (ЧЕКИ И ФК) ============
@client.on(events.NewMessage(chats=GMINES_CHAT))
async def gmines_handler(event):
    text_to_search = event.raw_text
    text_lower = text_to_search.lower().strip()
    
    # --- Логика ФК в gmineschat ---
    if text_lower.startswith("фк"):
        match_prefix = re.match(r'^фк\s*(?:\d+(?:\.\d*)?[кkмm]*)?\s*', text_to_search, re.IGNORECASE)
        content = text_to_search[match_prefix.end():].strip() if match_prefix else ""
        
        answer = "а" # Ответ по умолчанию
        if content:
            match_keyword = re.search(r'(?:пароль|капча)[:\s]*([^\s]+)', content, re.IGNORECASE)
            answer = match_keyword.group(1) if match_keyword else (content.split()[0] if content.split() else "а")
        
        try:
            await event.reply(answer)
            print(f"[{GMINES_CHAT}] Ответил на ФК: '{text_to_search}' -> '{answer}'")
        except Exception as e:
            print(f"[{GMINES_CHAT} - Ошибка ФК] Не удалось ответить: {e}")
        return # Выходим, чтобы не путать с чеком

    # --- Логика ПОИСКА ЧЕКОВ в gmineschat ---
    check_code = None
    match = re.search(r'start=(check_[a-zA-Z0-9_]+)', text_to_search)
    if match:
        check_code = match.group(1)

    # Ищем код чека в кнопках, если не нашли в тексте
    if not check_code and event.reply_markup:
        for row in event.reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, 'url') and TARGET_BOT in button.url:
                    m = re.search(r'start=(check_[a-zA-Z0-9_]+)', button.url)
                    if m: check_code = m.group(1)
    
    if check_code:
        try:
            await client.send_message(TARGET_BOT, f"/start {check_code}")
            print(f"[{GMINES_CHAT}] Нашел чек: {check_code}! Активирую в @{TARGET_BOT}...")
        except Exception as e:
            print(f"[Ошибка] Не удалось отправить чек боту {TARGET_BOT}: {e}")

# ============ ОБРАБОТЧИК 2: КЛИКЕР КНОПОК В GMINESBOT ============
@client.on(events.NewMessage(chats=TARGET_BOT))
@client.on(events.MessageEdited(chats=TARGET_BOT))
async def mines_bot_clicker(event):
    if event.reply_markup:
        for i, row in enumerate(event.reply_markup.rows):
            for j, button in enumerate(row.buttons):
                btn_text = button.text.lower()
                if "получить" in btn_text or "забрать" in btn_text:
                    try:
                        await event.click(i, j)
                        print(f"[+] В @{TARGET_BOT} успешно кликнул на кнопку '{button.text}'!")
                        return # Выходим после клика
                    except Exception as e:
                        print(f"[Ошибка] Не удалось кликнуть на кнопку '{button.text}' в @{TARGET_BOT}: {e}")

# ============ ОБРАБОТЧИК 3: ОБЩИЙ ДЛЯ КОММЕНТАРИЕВ "ФК" В ЧАТАХ ОБСУЖДЕНИЯ ============
@client.on(events.NewMessage(chats=COMMENT_TARGET_CHATS))
async def channel_comment_handler(event):
    if not SOURCE_CHANNEL_IDS_MAP:
        print("Ошибка: SOURCE_CHANNEL_IDS_MAP не инициализирован. Проверьте конфигурацию.")
        return

    # Определяем ID канала, из которого было переслано сообщение
    forwarded_from_channel_id = None
    if event.fwd_from and isinstance(event.fwd_from.from_id, PeerChannel):
        forwarded_from_channel_id = event.fwd_from.from_id.channel_id
    elif event.message.from_id and isinstance(event.message.from_id, PeerChannel):
        forwarded_from_channel_id = event.message.from_id.channel_id

    # Проверяем, что сообщение пришло именно из одного из наших мониторящихся каналов
    if forwarded_from_channel_id in SOURCE_CHANNEL_IDS_MAP:
        source_channel_username = SOURCE_CHANNEL_IDS_MAP[forwarded_from_channel_id]
        current_chat_username = event.chat.username if event.chat.username else f"ID:{event.chat.id}"

        text_to_search = event.raw_text
        text_lower = text_to_search.lower().strip()

        # Если пост начинается с "ФК"
        if text_lower.startswith("фк"):
            answer = "а" # Ответ по умолчанию
            if "пик" in text_lower:
                answer = "краш 5кк 2.13"
            else:
                m = re.search(r'(?:пароль|капча)[:\s]*([^\s]+)', text_to_search, re.IGNORECASE)
                answer = m.group(1) if m else "а"
            
            try:
                await event.reply(answer)
                print(f"[Коммент - @{current_chat_username}] Ответил на ФК из @{source_channel_username}: '{text_to_search}' -> '{answer}'")
            except Exception as e:
                print(f"[Коммент - Ошибка @{current_chat_username}] Не удалось ответить на ФК из @{source_channel_username}: {e}")
    # else:
    #     print(f"Пропустил сообщение в @{event.chat.username} от неизвестного канала: {event.raw_text[:50]}...") # Отладочная строка, можно раскомментировать

# ============ ЗАПУСК ЮЗЕРБОТА ============
async def main():
    global SOURCE_CHANNEL_IDS_MAP
    await client.start()
    
    me = await client.get_me()
    print(f"Юзербот успешно запущен под аккаунтом: {me.first_name} (ID: {me.id})")
    
    print("\n--- Инициализация мониторинга каналов для комментариев ФК ---")
    for config in CHANNEL_COMMENT_CONFIGS:
        try:
            source_entity = await client.get_input_entity(config['source'])
            SOURCE_CHANNEL_IDS_MAP[source_entity.channel_id] = config['source'] # Сохраняем ID и юзернейм
            print(f"  ✅ Мониторю посты из @{config['source']} (ID: {source_entity.channel_id}) для комментариев в @{config['target']}")
        except Exception as e:
            print(f"  ❌ Ошибка при доступе к каналу @{config['source']}: {e}")
            print("     Убедитесь, что аккаунт подписан на канал и @username указан верно.")
            # Можно добавить sys.exit() здесь, если вы хотите, чтобы бот не запускался при ошибке конфигурации
            
    print(f"-------------------------------------------------------------")
    print(f"1. Ловля чеков и авто-ФК в чате: @{GMINES_CHAT}")
    print(f"2. Авто-кнопки 'Получить'/'Забрать' в боте: @{TARGET_BOT}")
    print(f"3. Комментарии под постами ФК в чатах: {', '.join(COMMENT_TARGET_CHATS)}")
    print("-------------------------------------------------------------")
    print("Бот готов к работе. Ожидаю активности...")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
