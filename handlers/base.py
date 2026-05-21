from state_manager import USER_STATES
from keyboards import REPLY_KEYBOARD, INLINE_START_KEYBOARD
from utils import send_telegram_message

async def handle_start_command(chat_id: int, first_name: str):
    USER_STATES.pop(chat_id, None)
    bienvenida = f"¡Hola {first_name or 'usuario'}! Soy tu asistente financiero. ¿Qué deseas registrar hoy?"
    await send_telegram_message(chat_id, bienvenida, reply_markup=INLINE_START_KEYBOARD)

async def handle_cancel_command(chat_id: int):
    USER_STATES.pop(chat_id, None)
    await send_telegram_message(
        chat_id, 
        "❌ *Acción cancelada.* ¿En qué más puedo ayudarte hoy?", 
        reply_markup=REPLY_KEYBOARD
    )

async def handle_help_command(chat_id: int):
    ayuda_msg = (
        "💡 *Menú de Ayuda*\n\n"
        "• Presiona *📝 Registrar Transacción* para iniciar el registro guiado de ingresos y gastos.\n"
        "• Presiona *💳 Mis Cuentas* para listar tus cuentas financieras o añadir una nueva.\n"
        "• Presiona *💸 Deudas* para registrar o amortizar deudas.\n"
        "• Presiona *🔄 Últimos Movimientos* para revisar tu historial reciente.\n"
        "• Escribe *Cancelar* en cualquier momento para cancelar la operación actual.\n\n"
        "Este bot está configurado para registrar tus finanzas de forma segura y precisa."
    )
    await send_telegram_message(chat_id, ayuda_msg, reply_markup=REPLY_KEYBOARD)

async def handle_base_callbacks(chat_id: int, user_uuid: str, callback_data: str, message_id: int, callback_id: str, user_state: dict):
    if callback_data == "menu_back_start":
        await send_telegram_message(
            chat_id,
            "¡Hola! ¿Qué deseas registrar hoy?",
            reply_markup=INLINE_START_KEYBOARD
        )
