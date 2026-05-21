import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
SUPERADMIN_ID_STR = os.environ.get("SUPERADMIN_TELEGRAM_ID")
SUPERADMIN_ID = int(SUPERADMIN_ID_STR) if SUPERADMIN_ID_STR and SUPERADMIN_ID_STR.isdigit() else None

# ==========================================
# CONSTANTES DE MAPEO Y DICCIONARIOS GLOBALES
# ==========================================
ACCOUNT_TYPE_ICONS = {
    "efectivo": "💵 Efectivo",
    "debito": "💳 Débito",
    "tarjeta_credito": "💳 Tarjeta de Crédito",
    "ahorros": "🏦 Ahorros"
}

TX_TYPE_LABELS = {
    "ingreso": "📥 Ingreso",
    "gasto": "📤 Gasto" if "gasto" else "📤 Egreso / Gasto",  # Consistent with current main.py (📤 Egreso / Gasto)
    "transferencia": "🔄 Otro / Transferencia"
}

# Overriding slightly for exact main.py values:
TX_TYPE_LABELS["gasto"] = "📤 Egreso / Gasto"

# Iconos simplificados para resúmenes compactos e historiales
TX_TYPE_ICONS = {
    "ingreso": "📥 Ingreso",
    "gasto": "📤 Gasto",
    "transferencia": "🔄 Transferencia"
}
