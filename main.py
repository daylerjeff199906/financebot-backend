import os
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

# Database and AI functions needed for basic routing in main.py
from db import (
    get_user_by_telegram_id,
    create_user_by_telegram_id
)
from ai import parse_finance_text

# Modular Constants, State, Keyboards, and Utils
from constants import WEBHOOK_SECRET, SUPERADMIN_ID
from state_manager import (
    USER_STATES,
    ACCOUNT_STATES,
    DEBT_STATES,
    TRANSACTION_STATES
)
from keyboards import REPLY_KEYBOARD, INLINE_TYPE_KEYBOARD, INLINE_CONFIRM_KEYBOARD
from utils import send_telegram_message, edit_telegram_message, answer_callback_query

# Modular Handlers
from handlers.base import (
    handle_start_command,
    handle_cancel_command,
    handle_help_command,
    handle_base_callbacks
)
from handlers.accounts import (
    handle_accounts_menu,
    handle_accounts_callbacks,
    handle_accounts_states
)
from handlers.debts import (
    handle_debts_menu,
    handle_debts_callbacks,
    handle_debts_states
)
from handlers.transactions import (
    handle_resumen_menu,
    handle_movimientos_menu,
    handle_transactions_callbacks,
    handle_transactions_states
)

load_dotenv()

app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    # Validar el token de seguridad del Webhook para evitar peticiones falsas
    if WEBHOOK_SECRET:
        telegram_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if telegram_secret != WEBHOOK_SECRET:
            print("Intento de acceso no autorizado: Token de webhook incorrecto o ausente.")
            raise HTTPException(status_code=403, detail="Unauthorized webhook request")

    data = await request.json()

    # 1. Manejo de Callback Queries (clics en botones inline)
    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]
        callback_data = callback.get("data", "")

        # Responder de inmediato a Telegram para quitar el spinner
        await answer_callback_query(callback_id)

        # Obtener UUID de usuario
        user_uuid = get_user_by_telegram_id(chat_id)
        if not user_uuid:
            # Si por alguna razón no existe, lo creamos automáticamente
            sender = callback.get("from", {})
            user_uuid = create_user_by_telegram_id(
                telegram_id=chat_id,
                username=sender.get("username"),
                first_name=sender.get("first_name"),
                last_name=sender.get("last_name")
            )

        user_state = USER_STATES.get(chat_id, {})

        # Despachar Callback Query a los handlers correspondientes
        if callback_data.startswith(("account_detail:", "account_add:", "account_edit_name:", "account_edit_type:", "actype:", "accurr:")):
            await handle_accounts_callbacks(chat_id, user_uuid, callback_data, message_id, callback_id, user_state)
        elif callback_data.startswith(("menu_deudas", "debt_add:", "debttype:", "debtcurr:")):
            await handle_debts_callbacks(chat_id, user_uuid, callback_data, message_id, callback_id, user_state)
        elif callback_data.startswith(("reg_type:", "confirm_type:", "tx_acc:", "tx_date:", "tx_debt:", "menu_resumen", "menu_movimientos")):
            await handle_transactions_callbacks(chat_id, user_uuid, callback_data, message_id, callback_id, user_state)
        elif callback_data == "menu_back_start":
            await handle_base_callbacks(chat_id, user_uuid, callback_data, message_id, callback_id, user_state)

        return {"status": "ok"}

    # 2. Manejo de Mensajes Convencionales (texto)
    if "message" not in data or "text" not in data["message"]:
        return {"status": "ok"}

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"]["text"].strip()
    
    try:
        # Obtener los datos del remitente de Telegram
        sender = data["message"].get("from", {})
        username = sender.get("username")
        first_name = sender.get("first_name")
        last_name = sender.get("last_name")

        # Obtener o registrar el UUID del usuario en Supabase a partir de su ID de Telegram
        user_uuid = get_user_by_telegram_id(chat_id)
        is_new_user = False
        
        if not user_uuid:
            # Registrar automáticamente si no existe en la base de datos
            user_uuid = create_user_by_telegram_id(
                telegram_id=chat_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            if not user_uuid:
                from keyboards import INLINE_ERROR_KEYBOARD
                await send_telegram_message(
                    chat_id, 
                    "❌ Error crítico al registrar tu usuario automáticamente.",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                return {"status": "ok"}
            is_new_user = True

        # Determinar si es Superadmin
        is_superadmin = (SUPERADMIN_ID is not None and chat_id == SUPERADMIN_ID)

        # Si es un usuario nuevo, le enviamos una bienvenida personalizada
        if is_new_user:
            if is_superadmin:
                bienvenida = "👑 ¡Bienvenido, Superadmin! Has sido registrado automáticamente con privilegios totales."
            else:
                bienvenida = f"👋 ¡Hola {first_name or 'usuario'}! Te he registrado automáticamente en el sistema."
            await send_telegram_message(chat_id, bienvenida, reply_markup=REPLY_KEYBOARD)

        # Despachar Comandos o Estados
        command = user_text.lower()

        if command == "/start":
            await handle_start_command(chat_id, first_name)
        elif command in ["/cancelar", "cancelar", "❌ cancelar"]:
            await handle_cancel_command(chat_id)
        elif command in ["/ayuda", "ayuda", "❓ ayuda"]:
            await handle_help_command(chat_id)
        elif command in ["/cuentas", "cuentas", "💳 mis cuentas"]:
            await handle_accounts_menu(chat_id, user_uuid)
        elif command in ["/deudas", "deudas", "💸 deudas"]:
            await handle_debts_menu(chat_id, user_uuid)
        elif command in ["/resumen", "resumen", "📊 resumen"]:
            await handle_resumen_menu(chat_id, user_uuid)
        elif command in ["/movimientos", "movimientos", "🔄 últimos movimientos"]:
            await handle_movimientos_menu(chat_id, user_uuid)
        elif command in ["/registrar", "registrar", "📝 registrar transacción"]:
            USER_STATES[chat_id] = {
                "state": "AWAITING_TYPE"
            }
            await send_telegram_message(
                chat_id,
                "📊 *Registro de Transacción*\n\nPor favor, selecciona el tipo de transacción que deseas realizar:",
                reply_markup=INLINE_TYPE_KEYBOARD
            )
        else:
            # Lógica interactiva basada en Estados
            user_state = USER_STATES.get(chat_id)
            if user_state:
                state = user_state.get("state")
                if state in ACCOUNT_STATES:
                    await handle_accounts_states(chat_id, user_uuid, user_text, user_state)
                elif state in DEBT_STATES:
                    await handle_debts_states(chat_id, user_uuid, user_text, user_state)
                elif state in TRANSACTION_STATES:
                    await handle_transactions_states(chat_id, user_uuid, user_text, user_state)
            else:
                # Flujo por defecto con Inteligencia Artificial (Gemini)
                parsed_data = None
                try:
                    parsed_data = await parse_finance_text(user_text)
                except Exception as ai_err:
                    print(f"Error llamando a parse_finance_text: {ai_err}")

                if parsed_data and parsed_data.get("amount") and parsed_data.get("concept"):
                    amount = parsed_data["amount"]
                    concept = parsed_data["concept"]
                    tx_type = parsed_data.get("type", "gasto")
                    currency = parsed_data.get("currency", "PEN")
                    tx_date = parsed_data.get("date")

                    USER_STATES[chat_id] = {
                        "state": "CONFIRMING_PARSED_TX",
                        "amount": amount,
                        "concept": concept,
                        "type": tx_type,
                        "currency": currency,
                        "date": tx_date
                    }

                    from constants import TX_TYPE_LABELS
                    tipo_detectado = TX_TYPE_LABELS.get(tx_type, tx_type.capitalize())
                    fecha_detectada_msg = f"\n📅 *Fecha detectada:* {tx_date}" if tx_date else "\n📅 *Fecha:* Hoy"

                    mensaje_confirmar = (
                        f"🤖 *Detalles detectados por la IA:*\n\n"
                        f"💰 *Monto:* S/ {amount:.2f}\n"
                        f"📂 *Concepto:* {concept}\n"
                        f"💱 *Moneda:* {currency}"
                        f"{fecha_detectada_msg}\n"
                        f"🏷️ *Tipo sugerido:* {tipo_detectado}\n\n"
                        f"¿Cómo deseas registrar esta transacción? Selecciona una opción del menú de abajo para guardarla o cancelarla:"
                    )

                    await send_telegram_message(
                        chat_id,
                        mensaje_confirmar,
                        reply_markup=INLINE_CONFIRM_KEYBOARD
                    )
                else:
                    # Iniciar registro manual si la IA no logra discernir monto y concepto
                    USER_STATES[chat_id] = {
                        "state": "AWAITING_TYPE"
                    }
                    await send_telegram_message(
                        chat_id,
                        f"📊 *Registro de Transacción*\n\nHola {first_name or 'usuario'}. Por favor, selecciona el tipo de transacción que deseas registrar:",
                        reply_markup=INLINE_TYPE_KEYBOARD
                    )

    except Exception as e:
        print(f"Error general: {e}")
        from keyboards import INLINE_ERROR_KEYBOARD
        await send_telegram_message(
            chat_id, 
            "❌ Hubo un error interno al procesar tu solicitud.",
            reply_markup=INLINE_ERROR_KEYBOARD
        )

    return {"status": "ok"}
