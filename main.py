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
    get_user_transactions,
    update_user_account,
    get_user_debts,
    create_user_debt,
    get_debt_by_id,
    update_debt,
    get_user_transactions_current_month
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
        [{"text": "💳 Mis Cuentas"}, {"text": "💸 Deudas"}],
        [{"text": "🔄 Últimos Movimientos"}, {"text": "📊 Resumen"}],
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
            {"text": "💸 Deudas", "callback_data": "menu_deudas"}
        ],
        [
            {"text": "🔄 Últimos Movimientos", "callback_data": "menu_movimientos"},
            {"text": "📊 Resumen", "callback_data": "menu_resumen"}
        ],
        [
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

# --- NUEVOS AYUDANTES PARA EL FLUJO DE TRANSACCIONES ---

async def finish_transaction_registration(chat_id: int, user_uuid: str, user_state: dict, message_id: int = None):
    tx_type = user_state["type"]
    amount = user_state["amount"]
    concept = user_state["concept"]
    currency = user_state.get("currency", "PEN")
    account_id = user_state.get("account_id")
    tx_date = user_state.get("date")  # YYYY-MM-DD
    debt_id = user_state.get("debt_id")
    
    payload = {
        "user_id": user_uuid,
        "type": tx_type,
        "amount": amount,
        "concept": concept,
        "currency": currency,
        "account_id": account_id
    }
    
    if tx_date:
        payload["created_at"] = f"{tx_date}T12:00:00Z"
        
    if debt_id:
        payload["debt_id"] = debt_id
        
    try:
        # Inserta la transacción (actualiza el saldo de la cuenta automáticamente en db.py)
        insert_transaction(payload)
        
        debt_msg = ""
        if debt_id:
            debt = get_debt_by_id(debt_id)
            if debt:
                rem = float(debt["remaining_amount"])
                new_rem = max(0.0, rem - amount)
                new_status = "pagada" if new_rem == 0.0 else "pendiente"
                update_debt(debt_id, {
                    "remaining_amount": new_rem,
                    "status": new_status
                })
                sym = "S/" if currency == "PEN" else "$"
                debt_msg = f"\n\n💸 *Abono a Deuda:* Se amortizó la deuda de *{debt['description']}*.\n▪️ Pendiente Restante: *{sym} {new_rem:.2f}*"
                if new_status == "pagada":
                    debt_msg += " (¡Completamente pagada! 🎉)"
                    
        USER_STATES.pop(chat_id, None)
        
        label_map = {
            "ingreso": "📥 Ingreso",
            "gasto": "📤 Egreso / Gasto",
            "transferencia": "🔄 Transferencia"
        }
        tipo_label = label_map.get(tx_type, tx_type.capitalize())
        
        accounts = get_user_accounts(user_uuid)
        acc = next((a for a in accounts if a["id"] == account_id), None)
        acc_name = acc["name"] if acc else "Principal"
        
        sym = "S/" if currency == "PEN" else "$"
        fecha_str = tx_date or "Hoy"
        
        is_superadmin = (SUPERADMIN_ID is not None and chat_id == SUPERADMIN_ID)
        prefijo_admin = "[ADMIN] " if is_superadmin else ""
        
        mensaje_exito = (
            f"✅ {prefijo_admin}*¡Transacción Registrada!*\n\n"
            f"📅 *Detalles de la operación:*\n"
            f"▪️ *Tipo:* {tipo_label}\n"
            f"▪️ *Monto:* {sym} {amount:.2f}\n"
            f"▪️ *Concepto:* {concept}\n"
            f"▪️ *Cuenta:* {acc_name}\n"
            f"▪️ *Fecha:* {fecha_str}{debt_msg}\n\n"
            f"¡Gracias! Puedes seguir administrando tus finanzas desde el menú principal."
        )
        
        if message_id:
            await edit_telegram_message(chat_id, message_id, mensaje_exito)
        else:
            await send_telegram_message(chat_id, mensaje_exito, reply_markup=REPLY_KEYBOARD)
            
    except Exception as db_err:
        print(f"Error al registrar transaccion: {db_err}")
        err_msg = "⚠️ Hubo un problema al guardar la transacción. Por favor, intenta de nuevo."
        if message_id:
            await edit_telegram_message(chat_id, message_id, err_msg, reply_markup=INLINE_ERROR_KEYBOARD)
        else:
            await send_telegram_message(chat_id, err_msg, reply_markup=INLINE_ERROR_KEYBOARD)
        USER_STATES.pop(chat_id, None)

async def proceed_to_debt_check_or_finish(chat_id: int, user_uuid: str, user_state: dict, message_id: int = None):
    tx_type = user_state["type"]
    currency = user_state.get("currency", "PEN")
    
    if tx_type == "gasto":
        debts = get_user_debts(user_uuid)
        pending_debts = [d for d in debts if d["type"] == "por_pagar" and d["status"] == "pendiente" and d["currency"] == currency]
        
        if pending_debts:
            user_state["state"] = "AWAITING_TX_DEBT"
            USER_STATES[chat_id] = user_state
            
            inline_keyboard = []
            for d in pending_debts:
                desc = d["description"]
                rem = float(d["remaining_amount"])
                sym = "S/" if currency == "PEN" else "$"
                inline_keyboard.append([{"text": f"🔴 {desc} (Resta {sym} {rem:.2f})", "callback_data": f"tx_debt:{d['id']}"}])
            
            inline_keyboard.append([{"text": "🙅‍♂️ No, es un gasto común", "callback_data": "tx_debt:none"}])
            inline_keyboard.append([{"text": "❌ Cancelar Registro", "callback_data": "reg_type:cancel"}])
            
            msg = "💸 *¿Este gasto es para pagar alguna de tus deudas pendientes?*"
            if message_id:
                await edit_telegram_message(chat_id, message_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
            else:
                await send_telegram_message(chat_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
            return
            
    await finish_transaction_registration(chat_id, user_uuid, user_state, message_id)

async def prompt_for_date_selection(chat_id: int, user_state: dict, message_id: int = None):
    user_state["state"] = "AWAITING_TX_DATE"
    USER_STATES[chat_id] = user_state
    
    inline_keyboard = []
    
    parsed_date = user_state.get("date")
    if parsed_date:
        inline_keyboard.append([{"text": f"🤖 Usar fecha detectada ({parsed_date})", "callback_data": "tx_date:parsed"}])
        
    inline_keyboard.append([
        {"text": "📅 Hoy", "callback_data": "tx_date:today"},
        {"text": "📆 Ayer", "callback_data": "tx_date:yesterday"}
    ])
    inline_keyboard.append([
        {"text": "✍️ Otra Fecha (DD/MM/AAAA)", "callback_data": "tx_date:custom"}
    ])
    inline_keyboard.append([
        {"text": "❌ Cancelar Registro", "callback_data": "reg_type:cancel"}
    ])
    
    msg = "📅 *Fecha de la Transacción*\n\n¿Cuándo se realizó esta operación? Selecciona una opción:"
    if message_id:
        await edit_telegram_message(chat_id, message_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
    else:
        await send_telegram_message(chat_id, msg, reply_markup={"inline_keyboard": inline_keyboard})

async def prompt_for_account_selection_or_proceed(chat_id: int, user_uuid: str, user_state: dict, message_id: int = None):
    tx_currency = user_state.get("currency", "PEN")
    accounts = get_user_accounts(user_uuid)
    
    matching_accounts = [acc for acc in accounts if acc["currency"] == tx_currency]
    
    if len(matching_accounts) > 1:
        user_state["state"] = "AWAITING_TX_ACCOUNT"
        USER_STATES[chat_id] = user_state
        
        inline_keyboard = []
        for acc in matching_accounts:
            name = acc["name"]
            bal = float(acc["current_balance"])
            sym = "S/" if tx_currency == "PEN" else "$"
            inline_keyboard.append([{"text": f"💳 {name} ({sym} {bal:.2f})", "callback_data": f"tx_acc:{acc['id']}"}])
            
        inline_keyboard.append([{"text": "❌ Cancelar Registro", "callback_data": "reg_type:cancel"}])
        
        msg = f"💳 *Selecciona la cuenta para esta transacción ({tx_currency}):*"
        if message_id:
            await edit_telegram_message(chat_id, message_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
        else:
            await send_telegram_message(chat_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
    else:
        if len(matching_accounts) == 1:
            account_id = matching_accounts[0]["id"]
        else:
            if not accounts:
                account_payload = {
                    "user_id": user_uuid,
                    "name": "Efectivo",
                    "type": "efectivo",
                    "currency": "PEN",
                    "initial_balance": 0.0,
                    "current_balance": 0.0
                }
                res = create_user_account(account_payload)
                account_id = res[0]["id"] if res else None
            else:
                account_id = accounts[0]["id"]
                
        user_state["account_id"] = account_id
        await prompt_for_date_selection(chat_id, user_state, message_id)

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

        if callback_data == "menu_resumen":
            accounts = get_user_accounts(user_uuid)
            txs = get_user_transactions_current_month(user_uuid)
            
            bal_pen = 0.0
            bal_usd = 0.0
            acc_details = ""
            
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
                bal = float(acc["current_balance"] or 0.0)
                sym = "S/" if curr == "PEN" else "$"
                
                if curr == "PEN":
                    bal_pen += bal
                else:
                    bal_usd += bal
                    
                acc_details += f"▪️ *{name}* ({tipo}): *{sym} {bal:.2f}*\n"
            
            if not accounts:
                acc_details = "_No tienes ninguna cuenta registrada aún._\n"
            
            gross_str = f"S/ {bal_pen:.2f}"
            if bal_usd > 0 or any(a["currency"] == "USD" for a in accounts):
                gross_str += f"  |  $ {bal_usd:.2f}"
                
            inc_pen = 0.0
            inc_usd = 0.0
            exp_pen = 0.0
            exp_usd = 0.0
            
            for t in txs:
                curr = t["currency"] or "PEN"
                amount = float(t["amount"] or 0.0)
                t_type = t["type"]
                
                if t_type == "ingreso":
                    if curr == "PEN":
                        inc_pen += amount
                    else:
                        inc_usd += amount
                elif t_type in ["gasto", "transferencia"]:
                    if curr == "PEN":
                        exp_pen += amount
                    else:
                        exp_usd += amount
            
            net_pen = inc_pen - exp_pen
            net_usd = inc_usd - exp_usd
            
            from datetime import datetime
            meses = [
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
            ]
            current_month_name = meses[datetime.now().month - 1]
            
            msg = (
                f"📊 *Resumen Financiero - {current_month_name} {datetime.now().year}*\n\n"
                f"💳 *Saldo por Cuentas:*\n"
                f"{acc_details}\n"
                f"-----------------------------------\n"
                f"💰 *Saldo Bruto Total (Suma de Cuentas):*\n"
                f"👉 *{gross_str}*\n\n"
                f"📈 *Estadísticas de este Mes:*\n"
                f"📥 *Ingresos:* S/ {inc_pen:.2f} | $ {inc_usd:.2f}\n"
                f"📤 *Gastos:* S/ {exp_pen:.2f} | $ {exp_usd:.2f}\n"
                f"⚖️ *Balance Neto:* *S/ {net_pen:.2f}* | *$ {net_usd:.2f}*\n\n"
                f"_El balance neto muestra la diferencia entre ingresos y gastos del mes actual._"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}]
                ]
            }
            await edit_telegram_message(chat_id, message_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        if callback_data == "menu_config":
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
            msg += "Selecciona una cuenta de abajo para ver detalles o editarla, o crea una nueva:\n\n"
            
            type_icons = {
                "efectivo": "💵 Efectivo",
                "debito": "💳 Débito",
                "tarjeta_credito": "💳 Tarjeta de Crédito",
                "ahorros": "🏦 Ahorros"
            }
            
            inline_keyboard = []
            
            if not accounts:
                msg += "_No tienes ninguna cuenta registrada aún._"
            else:
                for acc in accounts:
                    name = acc["name"]
                    tipo = type_icons.get(acc["type"], acc["type"].capitalize())
                    curr = acc["currency"] or "PEN"
                    sym = "S/" if curr == "PEN" else "$"
                    bal = float(acc["current_balance"])
                    msg += f"▪️ *{name}* ({tipo})\n   Saldo Actual: *{sym} {bal:.2f}*\n\n"
                    inline_keyboard.append([{"text": f"⚙️ Configurar {name}", "callback_data": f"account_detail:{acc['id']}"}])
            
            inline_keyboard.append([{"text": "➕ Añadir Nueva Cuenta", "callback_data": "account_add:start"}])
            inline_keyboard.append([{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}])
            
            keyboard = {"inline_keyboard": inline_keyboard}
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

        if callback_data.startswith("account_detail:"):
            account_id = callback_data.split(":")[1]
            accounts = get_user_accounts(user_uuid)
            acc = next((a for a in accounts if a["id"] == account_id), None)
            if not acc:
                await send_telegram_message(chat_id, "⚠️ Cuenta no encontrada.")
                return {"status": "ok"}
            
            type_icons = {
                "efectivo": "💵 Efectivo",
                "debito": "💳 Débito",
                "tarjeta_credito": "💳 Tarjeta de Crédito",
                "ahorros": "🏦 Ahorros"
            }
            name = acc["name"]
            tipo = type_icons.get(acc["type"], acc["type"].capitalize())
            curr = acc["currency"] or "PEN"
            sym = "S/" if curr == "PEN" else "$"
            bal = float(acc["current_balance"])
            
            msg = (
                f"💳 *Detalle de Cuenta*\n\n"
                f"▪️ *Nombre:* {name}\n"
                f"▪️ *Tipo:* {tipo}\n"
                f"▪️ *Moneda:* {curr}\n"
                f"▪️ *Saldo Actual:* {sym} {bal:.2f}\n\n"
                f"¿Qué acción deseas realizar?"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✏️ Editar Nombre", "callback_data": f"account_edit_name:{account_id}"},
                        {"text": "✏️ Editar Tipo", "callback_data": f"account_edit_type:{account_id}"}
                    ],
                    [
                        {"text": "🔙 Volver a Cuentas", "callback_data": "menu_accounts"}
                    ]
                ]
            }
            await edit_telegram_message(chat_id, message_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        if callback_data.startswith("account_edit_name:"):
            account_id = callback_data.split(":")[1]
            USER_STATES[chat_id] = {
                "state": "AWAITING_EDIT_ACCOUNT_NAME",
                "account_id": account_id
            }
            await send_telegram_message(
                chat_id,
                "✏️ *Editar Nombre de Cuenta*\n\nPor favor, escribe el **nuevo nombre** para tu cuenta:\n\n_(O escribe Cancelar para abortar)_"
            )
            return {"status": "ok"}

        if callback_data.startswith("account_edit_type:"):
            account_id = callback_data.split(":")[1]
            USER_STATES[chat_id] = {
                "state": "AWAITING_EDIT_ACCOUNT_TYPE",
                "account_id": account_id
            }
            await edit_telegram_message(
                chat_id,
                message_id,
                "✏️ *Editar Tipo de Cuenta*\n\nSelecciona el **nuevo tipo** de cuenta usando los botones de abajo:",
                reply_markup=INLINE_ACTYPE_KEYBOARD
            )
            return {"status": "ok"}

        if callback_data.startswith("actype:"):
            actype = callback_data.split(":")[1]
            if actype == "cancel":
                USER_STATES.pop(chat_id, None)
                await edit_telegram_message(chat_id, message_id, "❌ *Operación cancelada.*", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") not in ["AWAITING_ACCOUNT_TYPE", "AWAITING_EDIT_ACCOUNT_TYPE"]:
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada o inválida.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
            
            if user_state.get("state") == "AWAITING_EDIT_ACCOUNT_TYPE":
                account_id = user_state["account_id"]
                try:
                    update_user_account(account_id, {"type": actype})
                    type_icons = {
                        "efectivo": "💵 Efectivo",
                        "debito": "💳 Débito",
                        "tarjeta_credito": "💳 Tarjeta de Crédito",
                        "ahorros": "🏦 Ahorros"
                    }
                    tipo_label = type_icons.get(actype, actype.capitalize())
                    USER_STATES.pop(chat_id, None)
                    await edit_telegram_message(
                        chat_id,
                        message_id,
                        f"✅ *¡Tipo de Cuenta Actualizado!*\n\nEl tipo ha sido cambiado a: *{tipo_label}*",
                        reply_markup=INLINE_ERROR_KEYBOARD
                    )
                except Exception as err:
                    print(f"Error al editar tipo de cuenta: {err}")
                    await edit_telegram_message(chat_id, message_id, "❌ Error al actualizar el tipo de cuenta.", reply_markup=INLINE_ERROR_KEYBOARD)
                    USER_STATES.pop(chat_id, None)
                return {"status": "ok"}
            
            # Flujo clásico de creación
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
            USER_STATES[chat_id] = {
                "state": "AWAITING_AMOUNT",
                "type": tx_type
            }

            label_map = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Egreso / Gasto",
                "transferencia": "🔄 Otro / Transferencia"
            }
            tipo_label = label_map.get(tx_type, tx_type.capitalize())

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

            user_state["type"] = tx_type
            # Redirigir a selección de cuenta interactiva (que luego va a fecha y deudas)
            await prompt_for_account_selection_or_proceed(chat_id, user_uuid, user_state, message_id)
            return {"status": "ok"}

        # --- HANDLERS PARA GESTIÓN DE DEUDAS ---
        
        if callback_data == "menu_deudas":
            debts = get_user_debts(user_uuid)
            
            por_pagar_msg = ""
            por_cobrar_msg = ""
            
            for d in debts:
                desc = d["description"]
                amount = float(d["amount"])
                rem = float(d["remaining_amount"])
                curr = d["currency"] or "PEN"
                sym = "S/" if curr == "PEN" else "$"
                status_icon = "⏳" if d["status"] == "pendiente" else "✅"
                
                line = f"▪️ *{desc}*: {sym} {rem:.2f} de {sym} {amount:.2f} {status_icon}\n"
                
                if d["type"] == "por_pagar":
                    por_pagar_msg += line
                else:
                    por_cobrar_msg += line
                    
            if not por_pagar_msg:
                por_pagar_msg = "_No tienes deudas por pagar registradas._\n"
            if not por_cobrar_msg:
                por_cobrar_msg = "_No tienes deudas por cobrar registradas._\n"
                
            msg = (
                f"💸 *Gestión de Deudas y Préstamos*\n\n"
                f"🔴 *Deudas Por Pagar (Tú debes):*\n"
                f"{por_pagar_msg}\n"
                f"🟢 *Deudas Por Cobrar (Te deben):*\n"
                f"{por_cobrar_msg}\n"
                f"_Registrar tus deudas te permite enlazarlas a tus gastos futuros para amortizarlas automáticamente._"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ Registrar Nueva Deuda", "callback_data": "debt_add:start"}],
                    [{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}]
                ]
            }
            await edit_telegram_message(chat_id, message_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        if callback_data == "debt_add:start":
            USER_STATES[chat_id] = {
                "state": "AWAITING_DEBT_DESC"
            }
            await send_telegram_message(
                chat_id,
                "➕ *Registrar Nueva Deuda*\n\nPor favor, escribe una **descripción** o nombre de la deuda (ejemplo: `Préstamo de Juan`, `Banco de la Nación`, `Préstamo a María`):\n\n_(Escribe Cancelar para abortar)_"
            )
            return {"status": "ok"}

        if callback_data.startswith("debttype:"):
            debttype = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_DEBT_TYPE":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
                
            user_state["type"] = debttype
            user_state["state"] = "AWAITING_DEBT_CURRENCY"
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🇵🇪 PEN (Soles)", "callback_data": "debtcurr:PEN"},
                        {"text": "🇺🇸 USD (Dólares)", "callback_data": "debtcurr:USD"}
                    ],
                    [{"text": "❌ Cancelar", "callback_data": "reg_type:cancel"}]
                ]
            }
            
            await edit_telegram_message(
                chat_id,
                message_id,
                "💱 *Selecciona la moneda de la deuda:*",
                reply_markup=keyboard
            )
            return {"status": "ok"}

        if callback_data.startswith("debtcurr:"):
            debtcurr = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_DEBT_CURRENCY":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
                
            user_state["currency"] = debtcurr
            user_state["state"] = "AWAITING_DEBT_AMOUNT"
            
            await edit_telegram_message(
                chat_id,
                message_id,
                f"💰 *Has seleccionado:* {debtcurr}\n\nPor favor, escribe el **monto total** de la deuda (ejemplo: `150` o `500.00`):"
            )
            return {"status": "ok"}

        # --- CALLBACKS DEL FLUJO DE REGISTRO UNIFICADO ---
        
        if callback_data.startswith("tx_acc:"):
            account_id = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_TX_ACCOUNT":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
                
            user_state["account_id"] = account_id
            # Avanzar a fecha
            await prompt_for_date_selection(chat_id, user_state, message_id)
            return {"status": "ok"}

        if callback_data.startswith("tx_date:"):
            date_type = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_TX_DATE":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
                
            from datetime import datetime, timedelta
            
            if date_type == "today":
                # Guardamos como None (usará la hora de Supabase al insertar) o el string de hoy
                user_state["date"] = datetime.now().strftime("%Y-%m-%d")
                await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
                
            elif date_type == "yesterday":
                yesterday = datetime.now() - timedelta(days=1)
                user_state["date"] = yesterday.strftime("%Y-%m-%d")
                await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
                
            elif date_type == "parsed":
                # Mantiene la fecha detectada por la IA
                await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
                
            elif date_type == "custom":
                user_state["state"] = "AWAITING_TX_CUSTOM_DATE"
                USER_STATES[chat_id] = user_state
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "✍️ *Ingresa la Fecha de la Operación*\n\nEscribe la fecha en formato **DD/MM/AAAA** (ejemplo: `15/05/2026` o `02/11/2025`):"
                )
            return {"status": "ok"}

        if callback_data.startswith("tx_debt:"):
            debt_id = callback_data.split(":")[1]
            user_state = USER_STATES.get(chat_id)
            if not user_state or user_state.get("state") != "AWAITING_TX_DEBT":
                await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
                return {"status": "ok"}
                
            if debt_id != "none":
                user_state["debt_id"] = debt_id
                
            await finish_transaction_registration(chat_id, user_uuid, user_state, message_id)
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
            msg += "Selecciona una cuenta de abajo para ver detalles o editarla, o crea una nueva:\n\n"
            
            type_icons = {
                "efectivo": "💵 Efectivo",
                "debito": "💳 Débito",
                "tarjeta_credito": "💳 Tarjeta de Crédito",
                "ahorros": "🏦 Ahorros"
            }
            
            inline_keyboard = []
            
            if not accounts:
                msg += "_No tienes ninguna cuenta registrada aún._"
            else:
                for acc in accounts:
                    name = acc["name"]
                    tipo = type_icons.get(acc["type"], acc["type"].capitalize())
                    curr = acc["currency"] or "PEN"
                    sym = "S/" if curr == "PEN" else "$"
                    bal = float(acc["current_balance"])
                    msg += f"▪️ *{name}* ({tipo})\n   Saldo Actual: *{sym} {bal:.2f}*\n\n"
                    inline_keyboard.append([{"text": f"⚙️ Configurar {name}", "callback_data": f"account_detail:{acc['id']}"}])
            
            inline_keyboard.append([{"text": "➕ Añadir Nueva Cuenta", "callback_data": "account_add:start"}])
            inline_keyboard.append([{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}])
            
            keyboard = {"inline_keyboard": inline_keyboard}
            await send_telegram_message(chat_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        # Manejar comando de Deudas o botón de Deudas
        if user_text.lower() in ["/deudas", "deudas", "💸 deudas"]:
            debts = get_user_debts(user_uuid)
            
            por_pagar_msg = ""
            por_cobrar_msg = ""
            
            for d in debts:
                desc = d["description"]
                amount = float(d["amount"])
                rem = float(d["remaining_amount"])
                curr = d["currency"] or "PEN"
                sym = "S/" if curr == "PEN" else "$"
                status_icon = "⏳" if d["status"] == "pendiente" else "✅"
                
                line = f"▪️ *{desc}*: {sym} {rem:.2f} de {sym} {amount:.2f} {status_icon}\n"
                
                if d["type"] == "por_pagar":
                    por_pagar_msg += line
                else:
                    por_cobrar_msg += line
                    
            if not por_pagar_msg:
                por_pagar_msg = "_No tienes deudas por pagar registradas._\n"
            if not por_cobrar_msg:
                por_cobrar_msg = "_No tienes deudas por cobrar registradas._\n"
                
            msg = (
                f"💸 *Gestión de Deudas y Préstamos*\n\n"
                f"🔴 *Deudas Por Pagar (Tú debes):*\n"
                f"{por_pagar_msg}\n"
                f"🟢 *Deudas Por Cobrar (Te deben):*\n"
                f"{por_cobrar_msg}\n"
                f"_Registrar tus deudas te permite enlazarlas a tus gastos futuros para amortizarlas automáticamente._"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ Registrar Nueva Deuda", "callback_data": "debt_add:start"}],
                    [{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}]
                ]
            }
            await send_telegram_message(chat_id, msg, reply_markup=keyboard)
            return {"status": "ok"}

        # Manejar comando de Resumen o botón de Resumen
        if user_text.lower() in ["/resumen", "resumen", "📊 resumen"]:
            accounts = get_user_accounts(user_uuid)
            txs = get_user_transactions_current_month(user_uuid)
            
            bal_pen = 0.0
            bal_usd = 0.0
            acc_details = ""
            
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
                bal = float(acc["current_balance"] or 0.0)
                sym = "S/" if curr == "PEN" else "$"
                
                if curr == "PEN":
                    bal_pen += bal
                else:
                    bal_usd += bal
                    
                acc_details += f"▪️ *{name}* ({tipo}): *{sym} {bal:.2f}*\n"
            
            if not accounts:
                acc_details = "_No tienes ninguna cuenta registrada aún._\n"
            
            gross_str = f"S/ {bal_pen:.2f}"
            if bal_usd > 0 or any(a["currency"] == "USD" for a in accounts):
                gross_str += f"  |  $ {bal_usd:.2f}"
                
            inc_pen = 0.0
            inc_usd = 0.0
            exp_pen = 0.0
            exp_usd = 0.0
            
            for t in txs:
                curr = t["currency"] or "PEN"
                amount = float(t["amount"] or 0.0)
                t_type = t["type"]
                
                if t_type == "ingreso":
                    if curr == "PEN":
                        inc_pen += amount
                    else:
                        inc_usd += amount
                elif t_type in ["gasto", "transferencia"]:
                    if curr == "PEN":
                        exp_pen += amount
                    else:
                        exp_usd += amount
            
            net_pen = inc_pen - exp_pen
            net_usd = inc_usd - exp_usd
            
            from datetime import datetime
            meses = [
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
            ]
            current_month_name = meses[datetime.now().month - 1]
            
            msg = (
                f"📊 *Resumen Financiero - {current_month_name} {datetime.now().year}*\n\n"
                f"💳 *Saldo por Cuentas:*\n"
                f"{acc_details}\n"
                f"-----------------------------------\n"
                f"💰 *Saldo Bruto Total (Suma de Cuentas):*\n"
                f"👉 *{gross_str}*\n\n"
                f"📈 *Estadísticas de este Mes:*\n"
                f"📥 *Ingresos:* S/ {inc_pen:.2f} | $ {inc_usd:.2f}\n"
                f"📤 *Gastos:* S/ {exp_pen:.2f} | $ {exp_usd:.2f}\n"
                f"⚖️ *Balance Neto:* *S/ {net_pen:.2f}* | *$ {net_usd:.2f}*\n\n"
                f"_El balance neto muestra la diferencia entre ingresos y gastos del mes actual._"
            )
            
            keyboard = {
                "inline_keyboard": [
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

        # Máquina de estados para el registro estructurado y configuraciones
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
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una opción usando los botones de abajo:*",
                    reply_markup=INLINE_TYPE_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_AMOUNT":
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
                user_state["concept"] = concept
                user_state["currency"] = "PEN"  # Por defecto en el flujo manual simple es PEN
                
                # Redirigir al flujo interactivo de selección de cuenta (que luego va a fecha y deudas)
                await prompt_for_account_selection_or_proceed(chat_id, user_uuid, user_state)
                return {"status": "ok"}

            elif state == "AWAITING_TX_ACCOUNT":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una cuenta usando los botones de abajo:*",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_TX_DATE":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una fecha usando los botones de abajo:*",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_TX_CUSTOM_DATE":
                from datetime import datetime
                try:
                    fecha_obj = datetime.strptime(user_text, "%d/%m/%Y")
                    user_state["date"] = fecha_obj.strftime("%Y-%m-%d")
                    # Avanzar a deuda
                    await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state)
                except ValueError:
                    await send_telegram_message(
                        chat_id,
                        "⚠️ *Fecha inválida.* Por favor, ingresa la fecha en formato **DD/MM/AAAA** (ejemplo: `15/05/2026`):"
                    )
                return {"status": "ok"}

            elif state == "AWAITING_TX_DEBT":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona una deuda usando los botones de abajo o indica que no es para pagar deudas:*",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
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
                
                USER_STATES.pop(chat_id, None)
                
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

            elif state == "AWAITING_EDIT_ACCOUNT_NAME":
                account_id = user_state["account_id"]
                new_name = user_text
                try:
                    update_user_account(account_id, {"name": new_name})
                    USER_STATES.pop(chat_id, None)
                    await send_telegram_message(
                        chat_id,
                        f"✅ *¡Nombre de Cuenta Actualizado!*\n\nEl nombre ha sido cambiado a: *{new_name}*",
                        reply_markup=REPLY_KEYBOARD
                    )
                except Exception as err:
                    print(f"Error al actualizar nombre de cuenta: {err}")
                    await send_telegram_message(chat_id, "❌ Error al actualizar el nombre de la cuenta.", reply_markup=REPLY_KEYBOARD)
                    USER_STATES.pop(chat_id, None)
                return {"status": "ok"}

            elif state == "AWAITING_DEBT_DESC":
                user_state["description"] = user_text
                user_state["state"] = "AWAITING_DEBT_TYPE"
                
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "🔴 Por Pagar (Yo debo)", "callback_data": "debttype:por_pagar"},
                            {"text": "🟢 Por Cobrar (Me deben)", "callback_data": "debttype:por_cobrar"}
                        ],
                        [{"text": "❌ Cancelar", "callback_data": "reg_type:cancel"}]
                    ]
                }
                
                await send_telegram_message(
                    chat_id,
                    f"📂 *Descripción de la Deuda:* {user_text}\n\nPor favor, selecciona el **tipo de deuda**:",
                    reply_markup=keyboard
                )
                return {"status": "ok"}

            elif state == "AWAITING_DEBT_TYPE":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona el tipo de deuda usando los botones de abajo:*",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_DEBT_CURRENCY":
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Por favor, selecciona la moneda de la deuda usando los botones de abajo:*",
                    reply_markup=INLINE_ERROR_KEYBOARD
                )
                return {"status": "ok"}

            elif state == "AWAITING_DEBT_AMOUNT":
                clean_bal = user_text.replace("S/", "").replace("$", "").replace(",", ".").replace(" ", "")
                try:
                    amount = float(clean_bal)
                    if amount <= 0:
                        raise ValueError("El monto debe ser positivo.")
                except ValueError:
                    await send_telegram_message(
                        chat_id,
                        "⚠️ *Monto inválido.* Por favor, ingresa solo números positivos (ejemplo: `150` o `300.50`):"
                    )
                    return {"status": "ok"}
                
                desc = user_state["description"]
                dtype = user_state["type"]
                curr = user_state["currency"]
                
                debt_payload = {
                    "user_id": user_uuid,
                    "description": desc,
                    "type": dtype,
                    "currency": curr,
                    "amount": amount,
                    "remaining_amount": amount,
                    "status": "pendiente"
                }
                
                try:
                    create_user_debt(debt_payload)
                    USER_STATES.pop(chat_id, None)
                    
                    sym = "S/" if curr == "PEN" else "$"
                    type_str = "🔴 Por Pagar (Tú debes)" if dtype == "por_pagar" else "🟢 Por Cobrar (Te deben)"
                    
                    mensaje_exito = (
                        f"✅ *¡Deuda Registrada Exitosamente!*\n\n"
                        f"💸 *Detalles de la Deuda:*\n"
                        f"▪️ *Descripción:* {desc}\n"
                        f"▪️ *Tipo:* {type_str}\n"
                        f"▪️ *Moneda:* {curr}\n"
                        f"▪️ *Monto:* {sym} {amount:.2f}\n\n"
                        f"¡Gracias! Esta deuda ya figura en tu sistema de control."
                    )
                    await send_telegram_message(chat_id, mensaje_exito, reply_markup=REPLY_KEYBOARD)
                except Exception as db_err:
                    print(f"Error al guardar deuda: {db_err}")
                    await send_telegram_message(chat_id, "❌ Error al guardar la deuda en la base de datos.", reply_markup=REPLY_KEYBOARD)
                    USER_STATES.pop(chat_id, None)
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
            tx_date = parsed_data.get("date")

            USER_STATES[chat_id] = {
                "state": "CONFIRMING_PARSED_TX",
                "amount": amount,
                "concept": concept,
                "type": tx_type,
                "currency": currency,
                "date": tx_date
            }

            label_map = {
                "ingreso": "📥 Ingreso",
                "gasto": "📤 Egreso / Gasto",
                "transferencia": "🔄 Otro / Transferencia"
            }
            tipo_detectado = label_map.get(tx_type, tx_type.capitalize())
            
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
            return {"status": "ok"}

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


