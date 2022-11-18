from telethon import TelegramClient

from src import config

bot_client = TelegramClient('bot', config.api_id, config.api_hash)
