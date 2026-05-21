import httpx
from constants import TELEGRAM_API_URL

async def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json=payload
        )

async def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: dict = None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API_URL}/editMessageText",
            json=payload
        )

async def answer_callback_query(callback_query_id: str, text: str = None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API_URL}/answerCallbackQuery",
            json=payload
        )
