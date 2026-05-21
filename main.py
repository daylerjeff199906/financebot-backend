import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from ai import parse_finance_text
from db import (
    get_user_by_telegram_id,
    insert_transaction,
    create_user_by_telegram_id,
    get_user_accounts,
    create_user_account,
    get_user_transactions
)

load_dotenv()

app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
SUPERADMIN_ID_STR = os.environ.get("SUPERADMIN_TELEGRAM_ID")
SUPERADMIN_ID = int(SUPERADMIN_ID_STR) if SUPERADMIN_ID_STR and SUPERADMIN_ID_STR.isdigit() else None

# Estado global en memoria para registrar el flujo interactivo de los usuarios
USER_STATES = {}

# Teclado permanente de Telegram (Reply Keyboard)
REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "📝 Registrar Transacción"}],
        [{"text": "💳 Mis Cuentas"}, {"text": "🔄 Últimos Movimientos"}],
        [{"text": "❓ Ayuda"}, {"text": "❌ Cancelar"}]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}

# Menú inline para seleccionar tipo de transacción
INLINE_TYPE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📥 Ingreso", "callback_data": "reg_type:ingreso"},
            {"text": "📤 Egreso / Gasto", "callback_data": "reg_type:gasto"}
        ],
        [
            {"text": "🔄 Otro / Transferencia", "callback_data": "reg_type:transferencia"}
        ],
        [
            {"text": "❌ Cancelar Registro", "callback_data": "reg_type:cancel"}
        ]
    ]
}

# Menú inline para confirmar los detalles extraídos por la IA y escoger tipo
INLINE_CONFIRM_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📥 Confirmar Ingreso", "callback_data": "confirm_type:ingreso"},
            {"text": "📤 Confirmar Gasto", "callback_data": "confirm_type:gasto"}
        ],
        [
            {"text": "🔄 Confirmar Transferencia", "callback_data": "confirm_type:transferencia"}
        ],
        [
            {"text": "❌ Cancelar Registro", "callback_data": "confirm_type:cancel"}
        ]
    ]
}

# Menú principal (Start)
INLINE_START_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "💰 Gasto", "callback_data": "reg_type:gasto"},
            {"text": "💵 Ingreso", "callback_data": "reg_type:ingreso"}
        ],
        [
            {"text": "💳 Mis Cuentas", "callback_data": "menu_accounts"},
            {"text": "🔄 Últimos Movimientos", "callback_data": "menu_movimientos"}
        ],
        [
            {"text": "📊 Resumen", "callback_data": "menu_resumen"},
            {"text": "⚙️ Configuración", "callback_data": "menu_config"}
        ]
    ]
}

# Menú inline para seleccionar tipo de cuenta a añadir
INLINE_ACTYPE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "💵 Efectivo", "callback_data": "actype:efectivo"},
            {"text": "💳 Débito", "callback_data": "actype:debito"}
        ],
        [
            {"text": "💳 Tarjeta de Crédito", "callback_data": "actype:tarjeta_credito"},
            {"text": "🏦 Ahorros", "callback_data": "actype:ahorros"}
        ],
        [
            {"text": "❌ Cancelar Registro", "callback_data": "actype:cancel"}
        ]
    ]
}

# Menú inline para seleccionar la moneda de la cuenta a añadir
INLINE_ACCURR_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🇵🇪 PEN (Soles)", "callback_data": "accurr:PEN"},
            {"text": "🇺🇸 USD (Dólares)", "callback_data": "accurr:USD"}
        ],
        [
            {"text": "❌ Cancelar Registro", "callback_data": "accurr:cancel"}
        ]
    ]
}

# Menú inline para volver al inicio ante errores o cancelaciones
INLINE_ERROR_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}
        ]
    ]
}


# Funciones utilitarias para enviar mensajes de vuelta a Telegram
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

        if callback_data == "reg_type:cancel":
            USER_STATES.pop(chat_id, None)
            await edit_telegram_message(chat_id, message_id, "❌ *Registro cancelado.*", reply_markup=INLINE_ERROR_KEYBOARD)
            return {"status": "ok"}

        if callback_data in ["menu_resumen", "menu_config"]:
            if callback_data == "menu_resumen":
                await send_telegram_message(chat_id, "📊 *Resumen*: Aquí se sumarán los gastos e ingresos del mes (Funcionalidad en desarrollo).")
            elif callback_data == "menu_config":
                await send_telegram_message(chat_id, "⚙️ *Configuración*: Opciones de cuenta y preferencias (Funcionalidad en desarrollo).")
            return {"status": "ok"}

        if callback_data == "menu_movimientos":
            txs = get_user_transactions(user_uuid, limit=5)
            if not txs:
                await send_telegram_message(chat_id, "🔄 *Últimos Movimientos:*\n\nNo tienes transacciones registradas aún.")
                return {"status": "ok"}
            
            msg = "🔄 *Tus Últimos Movimientos:*\n\n"
            type_icons = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Gasto",
                "transferencia": "🔄 Transferencia"
            }
            for t in txs:
                icono = type_icons.get(t["type"], t["type"].capitalize())
                concept = t["concept"] or "Sin concepto"
                currency = t["currency"] or "PEN"
                symbol = "S/" if currency == "PEN" else "$"
                amount = float(t["amount"])
                fecha = t.get("created_at", "")[:10] if t.get("created_at") else ""
                fecha_str = f" _({fecha})_" if fecha else ""
                msg += f"▪️ {icono}: *{symbol} {amount:.2f}* - {concept}{fecha_str}\n"
            
            await send_telegram_message(chat_id, msg)
            return {"status": "ok"}

        if callback_data == "menu_accounts":
            accounts = get_user_accounts(user_uuid)
            msg = "💳 *Tus Cuentas Financieras:*\n\n"
            
            if not accounts:
                msg += "No tienes ninguna cuenta registrada. Por favor, crea una presionando el botón de abajo."
            else:
                type_icons = {
                    "efectivo": "💵 Efectivo",
                    "debito": "💳 Débito",
                    "tarjeta_credito": "💳 Tarjeta de Crédito",
                    "ahorros": "🏦 Ahorros"
                }
                for acc in accounts:
                    name = acc["name"]
                    tipo = type_icons.get(acc["type"], acc["type"].capitalize())
                    curr = acc["currency"] or "PEN"
                    sym = "S/" if curr == "PEN" else "$"
                    bal = float(acc["current_balance"])
                    msg += f"▪️ *{name}* ({tipo})\n   Saldo Actual: *{sym} {bal:.2f}*\n\n"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ Añadir Nueva Cuenta", "callback_data": "account_add:start"}],
                    [{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}]
                ]
            }
            await send_telegram_message(chat_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        if callback_data == "menu_back_start":
            await send_telegram_message(
                chat_id,
                "¡Hola! ¿Qué deseas registrar hoy?",
                reply_markup=INLINE_START_KEYBOARD
            )
            return {"status": "ok"}

        if callback_data == "account_add:start":
            USER_STATES[chat_id] = {
                "state": "AWAITING_ACCOUNT_NAME"
            }
            await send_telegram_message(
                chat_id,
                "➕ *Añadir Nueva Cuenta*\n\nPor favor, escribe el **nombre** de la cuenta (ejemplo: `Billetera`, `Cuenta de Ahorros BCP`, `Tarjeta BBVA`):\n\n_(Puedes escribir Cancelar para abortar)_"
            )
            return {"status": "ok"}

        if callback_data.startswith("actype:"):
            actype = callback_data.split(":")[1]
            if actype == "cancel":
                USER_STATES.pop(chat_id, None)
                await edit_telegram_message(chat_id, message_id, "❌ *Creación de cuenta cancelada.*", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_ACCOUNT_TYPE":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            user_state["type"] = actype
            user_state["state"] = "AWAITING_ACCOUNT_CURRENCY"
            
            await edit_telegram_message(
                chat_id,
                message_id,
                "💱 *Selecciona la moneda de la cuenta:*",
                reply_markup=INLINE_ACCURR_KEYBOARD
            )
            return {"status": "ok"}

        if callback_data.startswith("accurr:"):
            accurr = callback_data.split(":")[1]
            if accurr == "cancel":
                USER_STATES.pop(chat_id, None)
                await edit_telegram_message(chat_id, message_id, "❌ *Creación de cuenta cancelada.*", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_ACCOUNT_CURRENCY":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            user_state["currency"] = accurr
            user_state["state"] = "AWAITING_ACCOUNT_BALANCE"
            
            await edit_telegram_message(
                chat_id,
                message_id,
                f"💰 *Has seleccionado:* {accurr}\n\nPor favor, escribe el **saldo inicial** de la cuenta (ejemplo: `0` o `150.50`):"
            )
            return {"status": "ok"}

        if callback_data.startswith("reg_type:"):
            tx_type = callback_data.split(":")[1]
            # Guardar tipo seleccionado en el estado
            USER_STATES[chat_id] = {
                "state": "AWAITING_AMOUNT",
                "type": tx_type
            }

            # Mapeo a etiqueta amigable
            label_map = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Egreso / Gasto",
                "transferencia": "🔄 Otro / Transferencia"
            }
            tipo_label = label_map.get(tx_type, tx_type.capitalize())

            # Actualizar el mensaje de selección
            await edit_telegram_message(
                chat_id,
                message_id,
                f"💰 *Has seleccionado:* {tipo_label}\n\nPor favor, escribe el **monto** de la transacción (ejemplo: `25.50` o `100`):\n\n_(Puedes escribir /cancelar en cualquier momento)_"
            )
            return {"status": "ok"}

        if callback_data == "confirm_type:cancel":
            USER_STATES.pop(chat_id, None)
            await edit_telegram_message(chat_id, message_id, "❌ *Registro cancelado.*", reply_markup=INLINE_ERROR_KEYBOARD)
            return {"status": "ok"}

        if callback_data.startswith("confirm_type:"):
            tx_type = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "CONFIRMING_PARSED_TX":
                await edit_telegram_message(chat_id, message_id, "⚠️ *Error:* Sesión de confirmación expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}

            amount = user_state["amount"]
            concept = user_state["concept"]
            currency = user_state.get("currency", "PEN")

            # Construir el payload de la transacción
            transaction_payload = {
                "user_id": user_uuid,
                "type": tx_type,
                "amount": amount,
                "concept": concept,
                "currency": currency,
            }

            # Insertar en Supabase
            try:
                insert_transaction(transaction_payload)
            except Exception as db_err:
                print(f"Error al insertar transacción en Supabase: {db_err}")
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "⚠️ Hubo un problema al guardar la transacción en la base de datos. Por favor, intenta de nuevo.",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                USER_STATES.pop(chat_id, None)
                return {"status": "ok"}

            # Limpiar estado
            USER_STATES.pop(chat_id, None)

            # Mapeo a etiqueta amigable
            label_map = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Egreso / Gasto",
                "transferencia": "🔄 Otro / Transferencia"
            }
            tipo_label = label_map.get(tx_type, tx_type.capitalize())

            is_superadmin = (SUPERADMIN_ID is not None and chat_id == SUPERADMIN_ID)
            prefijo_admin = "[ADMIN] " if is_superadmin else ""

            # Mensaje de confirmación final
            mensaje_exito = (
                f"✅ {prefijo_admin}*¡Transacción Registrada!*\n\n"
                f"📅 *Detalles de la operación:*\n"
                f"▪️ *Tipo:* {tipo_label}\n"
                f"▪️ *Monto:* S/ {amount:.2f}\n"
                f"▪️ *Concepto:* {concept}\n"
                f"▪️ *Moneda:* {currency}\n\n"
                f"¡Gracias! Presiona el botón de abajo si deseas registrar otra transacción."
            )

            await edit_telegram_message(chat_id, message_id, mensaje_exito)
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

        # Manejar comando de Inicio (/start)
        if user_text.lower() == "/start":
            USER_STATES.pop(chat_id, None)
            bienvenida = f"¡Hola {first_name or 'usuario'}! Soy tu asistente financiero. ¿Qué deseas registrar hoy?"
            # Mostramos el menú inicial con botones inline
            await send_telegram_message(chat_id, bienvenida, reply_markup=INLINE_START_KEYBOARD)
            return {"status": "ok"}

        # Manejar comando de Cancelar
        if user_text.lower() in ["/cancelar", "cancelar", "❌ cancelar"]:
            USER_STATES.pop(chat_id, None)
            await send_telegram_message(
                chat_id, 
                "❌ *Acción cancelada.* ¿En qué más puedo ayudarte hoy?", 
                reply_markup=REPLY_KEYBOARD
            )
            return {"status": "ok"}

        # Manejar comando de Registro o botón de inicio
        if user_text.lower() in ["/registrar", "registrar", "📝 registrar transacción"]:
            # Inicializar el estado en Selección de Categoría
            USER_STATES[chat_id] = {
                "state": "AWAITING_TYPE"
            }
            await send_telegram_message(
                chat_id,
                "📊 *Registro de Transacción*\n\nPor favor, selecciona el tipo de transacción que deseas realizar:",
                reply_markup=INLINE_TYPE_KEYBOARD
            )
            return {"status": "ok"}

        # Manejar comando de Ayuda
        if user_text.lower() in ["/help", "/ayuda", "ayuda", "❓ ayuda"]:
            await send_telegram_message(
                chat_id,
                "💡 *Menú de Ayuda*\n\n"
                "• Presiona *📝 Registrar Transacción* para iniciar el registro guiado de ingresos y gastos.\n"
                "• Presiona *💳 Mis Cuentas* para listar tus cuentas financieras o añadir una nueva.\n"
                "• Presiona *🔄 Últimos Movimientos* para revisar tu historial reciente.\n"
                "• Escribe *Cancelar* en cualquier momento para cancelar la operación actual.\n\n"
                "Este bot está configurado para registrar tus finanzas de forma segura y precisa sin usar IA para inferir los datos.",
                reply_markup=REPLY_KEYBOARD
            )
            return {"status": "ok"}

        # Manejar comando de Cuentas o botón de Mis Cuentas
        if user_text.lower() in ["/cuentas", "cuentas", "💳 mis cuentas"]:
            accounts = get_user_accounts(user_uuid)
            msg = "💳 *Tus Cuentas Financieras:*\n\n"
            if not accounts:
                msg += "No tienes ninguna cuenta registrada. Por favor, crea una presionando el botón de abajo."
            else:
                type_icons = {
                    "efectivo": "💵 Efectivo",
                    "debito": "💳 Débito",
                    "tarjeta_credito": "💳 Tarjeta de Crédito",
                    "ahorros": "🏦 Ahorros"
                }
                for acc in accounts:
                    name = acc["name"]
                    tipo = type_icons.get(acc["type"], acc["type"].capitalize())
                    curr = acc["currency"] or "PEN"
                    sym = "S/" if curr == "PEN" else "$"
                    bal = float(acc["current_balance"])
                    msg += f"▪️ *{name}* ({tipo})\n   Saldo Actual: *{sym} {bal:.2f}*\n\n"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ Añadir Nueva Cuenta", "callback_data": "account_add:start"}],
                    [{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}]
                ]
            }
            await send_telegram_message(chat_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        # Manejar comando de Movimientos o botón de Últimos Movimientos
        if user_text.lower() in ["/movimientos", "movimientos", "🔄 últimos movimientos"]:
            txs = get_user_transactions(user_uuid, limit=5)
            if not txs:
                await send_telegram_message(chat_id, "🔄 *Últimos Movimientos:*\n\nNo tienes transacciones registradas aún.")
                return {"status": "ok"}
            
            msg = "🔄 *Tus Últimos Movimientos:*\n\n"
            type_icons = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Gasto",
                "transferencia": "🔄 Transferencia"
            }
            for t in txs:
                icono = type_icons.get(t["type"], t["type"].capitalize())
                concept = t["concept"] or "Sin concepto"
                currency = t["currency"] or "PEN"
                symbol = "S/" if currency == "PEN" else "$"
                amount = float(t["amount"])
                fecha = t.get("created_at", "")[:10] if t.get("created_at") else ""
                fecha_str = f" _({fecha})_" if fecha else ""
                msg += f"▪️ {icono}: *{symbol} {amount:.2f}* - {concept}{fecha_str}\n"
            
            await send_telegram_message(chat_id, msg, reply_markup=REPLY_KEYBOARD)
            return {"status": "ok"}

        # Máquina de estados para el registro estructurado
        user_state = USER_STATES.get(chat_id)
        if user_state:
            state = user_state.get("state")
            
            if state == "CONFIRMING_PARSED_TX":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una de las opciones del menú de abajo para guardar o cancelar la transacción:*",
                    reply_markup=INLINE_CONFIRM_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_TYPE":
                # El usuario debería usar los botones inline
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una opción usando los botones de abajo:*",
                    reply_markup=INLINE_TYPE_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_AMOUNT":
                # Limpiar caracteres comunes que puedan ingresar (ej. S/, $, comas)
                clean_amount = user_text.replace("S/", "").replace("$", "").replace(",", ".").replace(" ", "")
                try:
                    amount = float(clean_amount)
                    if amount <= 0:
                        raise ValueError("El monto debe ser positivo.")
                except ValueError:
                    await send_telegram_message(
                        chat_id,
                        "⚠️ *Monto inválido.* Por favor, ingresa solo números positivos (ejemplo: `25.50` o `120`):",
                        reply_markup=INLINE_ERROR_KEYBOARD
                    )
                    return {"status": "ok"}

                # Guardar monto y avanzar estado
                user_state["amount"] = amount
                user_state["state"] = "AWAITING_CONCEPT"
                
                label_map = {
                    "ingreso": "📥 Ingreso",
                    "gasto": "📤 Egreso / Gasto",
                    "transferencia": "🔄 Otro"
                }
                tipo_label = label_map.get(user_state["type"], user_state["type"].capitalize())

                await send_telegram_message(
                    chat_id,
                    f"💰 *Monto registrado:* S/ {amount:.2f}\n📂 *Categoría:* {tipo_label}\n\nAhora, escribe el **concepto** o descripción de la transacción (ejemplo: `Compras supermercado`, `Sueldo`):"
                )
                return {"status": "ok"}

            elif state == "AWAITING_CONCEPT":
                concept = user_text
                tx_type = user_state["type"]
                amount = user_state["amount"]

                # Construir el payload de la transacción
                transaction_payload = {
                    "user_id": user_uuid,
                    "type": tx_type,
                    "amount": amount,
                    "concept": concept,
                    "currency": "PEN",
                }

                # Insertar en Supabase
                try:
                    insert_transaction(transaction_payload)
                except Exception as db_err:
                    print(f"Error al insertar transacción en Supabase: {db_err}")
                    await send_telegram_message(
                        chat_id,
                        "⚠️ Hubo un problema al guardar la transacción en la base de datos. Por favor, intenta de nuevo.",
                        reply_markup=INLINE_ERROR_KEYBOARD
                    )
                    USER_STATES.pop(chat_id, None)
                    return {"status": "ok"}

                # Limpiar estado
                USER_STATES.pop(chat_id, None)

                # Mapeo a etiqueta amigable
                label_map = {
                    "ingreso": "📥 Ingreso",
                    "gasto": "📤 Egreso / Gasto",
                    "transferencia": "🔄 Otro"
                }
                tipo_label = label_map.get(tx_type, tx_type.capitalize())

                prefijo_admin = "[ADMIN] " if is_superadmin else ""
                
                # Mensaje Premium de confirmación
                mensaje_exito = (
                    f"✅ {prefijo_admin}*¡Transacción Registrada!*\n\n"
                    f"📅 *Detalles de la operación:*\n"
                    f"▪️ *Tipo:* {tipo_label}\n"
                    f"▪️ *Monto:* S/ {amount:.2f}\n"
                    f"▪️ *Concepto:* {concept}\n"
                    f"▪️ *Moneda:* PEN\n\n"
                    f"¡Gracias! Presiona el botón de abajo si deseas registrar otra transacción."
                )
                
                await send_telegram_message(chat_id, mensaje_exito, reply_markup=REPLY_KEYBOARD)
                return {"status": "ok"}

            elif state == "AWAITING_ACCOUNT_NAME":
                user_state["name"] = user_text
                user_state["state"] = "AWAITING_ACCOUNT_TYPE"
                
                await send_telegram_message(
                    chat_id,
                    f"📂 *Nombre de cuenta:* {user_text}\n\nSelecciona el **tipo de cuenta** usando los botones de abajo:",
                    reply_markup=INLINE_ACTYPE_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_ACCOUNT_TYPE":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona el tipo de cuenta usando los botones de abajo:*",
                    reply_markup=INLINE_ACTYPE_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_ACCOUNT_CURRENCY":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona la moneda de la cuenta usando los botones de abajo:*",
                    reply_markup=INLINE_ACCURR_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_ACCOUNT_BALANCE":
                clean_bal = user_text.replace("S/", "").replace("$", "").replace(",", ".").replace(" ", "")
                try:
                    balance = float(clean_bal)
                except ValueError:
                    await send_telegram_message(
                        chat_id,
                        "⚠️ *Saldo inválido.* Por favor, ingresa solo números (ejemplo: `0` o `150.50`):",
                        reply_markup=INLINE_ERROR_KEYBOARD
                    )
                    return {"status": "ok"}
                
                name = user_state["name"]
                actype = user_state["type"]
                currency = user_state["currency"]
                
                # Crear la cuenta
                account_payload = {
                    "user_id": user_uuid,
                    "name": name,
                    "type": actype,
                    "currency": currency,
                    "initial_balance": balance,
                    "current_balance": balance
                }
                
                try:
                    create_user_account(account_payload)
                except Exception as acc_err:
                    print(f"Error al crear cuenta en Supabase: {acc_err}")
                    await send_telegram_message(
                        chat_id,
                        "⚠️ Hubo un problema al crear la cuenta en la base de datos. Por favor, intenta de nuevo.",
                        reply_markup=INLINE_ERROR_KEYBOARD
                    )
                    USER_STATES.pop(chat_id, None)
                    return {"status": "ok"}
                
                # Limpiar estado
                USER_STATES.pop(chat_id, None)
                
                # Mapeo a etiqueta amigable
                type_labels = {
                    "efectivo": "💵 Efectivo",
                    "debito": "💳 Débito",
                    "tarjeta_credito": "💳 Tarjeta de Crédito",
                    "ahorros": "🏦 Ahorros"
                }
                type_label = type_labels.get(actype, actype.capitalize())
                curr_symbol = "S/" if currency == "PEN" else "$"
                
                mensaje_exito = (
                    f"✅ *¡Cuenta Creada Exitosamente!*\n\n"
                    f"💳 *Detalles de la Cuenta:*\n"
                    f"▪️ *Nombre:* {name}\n"
                    f"▪️ *Tipo:* {type_label}\n"
                    f"▪️ *Moneda:* {currency}\n"
                    f"▪️ *Saldo Inicial:* {curr_symbol} {balance:.2f}\n\n"
                    f"¡Gracias! Ya puedes usar esta cuenta para tus transacciones."
                )
                
                await send_telegram_message(chat_id, mensaje_exito, reply_markup=REPLY_KEYBOARD)
                return {"status": "ok"}

        # Si no está en ningún estado y el mensaje no es un comando conocido,
        # intentamos procesar el texto usando Inteligencia Artificial (Gemini)
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

            # Almacenar en memoria del usuario
            USER_STATES[chat_id] = {
                "state": "CONFIRMING_PARSED_TX",
                "amount": amount,
                "concept": concept,
                "type": tx_type,
                "currency": currency
            }

            # Map a etiqueta amigable
            label_map = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Egreso / Gasto",
                "transferencia": "🔄 Otro / Transferencia"
            }
            tipo_detectado = label_map.get(tx_type, tx_type.capitalize())

            mensaje_confirmar = (
                f"🤖 *Detalles detectados por la IA:*\n\n"
                f"💰 *Monto:* S/ {amount:.2f}\n"
                f"📂 *Concepto:* {concept}\n"
                f"💱 *Moneda:* {currency}\n"
                f"🏷️ *Tipo sugerido:* {tipo_detectado}\n\n"
                f"¿Cómo deseas registrar esta transacción? Selecciona una opción del menú de abajo para guardarla o cancelarla:"
            )

            await send_telegram_message(
                chat_id,
                mensaje_confirmar,
                reply_markup=INLINE_CONFIRM_KEYBOARD
            )
            return {"status": "ok"}

        # Si no se pudo extraer la información básica, iniciamos el flujo estructurado tradicional
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
        await send_telegram_message(
            chat_id, 
            "❌ Hubo un error interno al procesar tu solicitud.",
            reply_markup=INLINE_ERROR_KEYBOARD
        )

    return {"status": "ok"}


