import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
PUBLIC_URL = "https://financebot-backend-n034.onrender.com"

webhook_url = f"{PUBLIC_URL}/webhook"
telegram_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

payload = {
    "url": webhook_url,
    "secret_token": WEBHOOK_SECRET
}

print(f"Setting webhook to: {webhook_url}...")
try:
    response = httpx.post(telegram_api, json=payload)
    print("Response status code:", response.status_code)
    print("Response JSON:", response.json())
except Exception as e:
    print("Error setting webhook:", e)
