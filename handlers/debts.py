from keyboards import INLINE_ERROR_KEYBOARD, REPLY_KEYBOARD
from state_manager import USER_STATES
from utils import send_telegram_message, edit_telegram_message
from db import (
    get_user_debts,
    create_user_debt
)

async def handle_debts_menu(chat_id: int, user_uuid: str, edit_mode: bool = False, message_id: int = None):
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
    
    if edit_mode and message_id:
        await edit_telegram_message(chat_id, message_id, msg, reply_markup=keyboard)
    else:
        await send_telegram_message(chat_id, msg, reply_markup=keyboard)

async def handle_debts_callbacks(chat_id: int, user_uuid: str, callback_data: str, message_id: int, callback_id: str, user_state: dict):
    if callback_data == "menu_deudas":
        await handle_debts_menu(chat_id, user_uuid, edit_mode=True, message_id=message_id)
        return

    if callback_data == "debt_add:start":
        USER_STATES[chat_id] = {
            "state": "AWAITING_DEBT_DESC"
        }
        await send_telegram_message(
            chat_id,
            "➕ *Registrar Nueva Deuda*\n\nPor favor, escribe una **descripción** o nombre de la deuda (ejemplo: `Préstamo de Juan`, `Banco de la Nación`, `Préstamo a María`):\n\n_(Escribe Cancelar para abortar)_"
        )
        return

    if callback_data.startswith("debttype:"):
        debttype = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "AWAITING_DEBT_TYPE":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
            
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
        return

    if callback_data.startswith("debtcurr:"):
        debtcurr = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "AWAITING_DEBT_CURRENCY":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
            
        user_state["currency"] = debtcurr
        user_state["state"] = "AWAITING_DEBT_AMOUNT"
        
        await edit_telegram_message(
            chat_id,
            message_id,
            f"💰 *Has seleccionado:* {debtcurr}\n\nPor favor, escribe el **monto total** de la deuda (ejemplo: `150` o `500.00`):"
        )
        return

async def handle_debts_states(chat_id: int, user_uuid: str, user_text: str, user_state: dict):
    state = user_state.get("state")

    if state == "AWAITING_DEBT_DESC":
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
        return

    if state == "AWAITING_DEBT_TYPE":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona el tipo de deuda usando los botones de abajo:*",
            reply_markup=INLINE_ERROR_KEYBOARD
        )
        return

    if state == "AWAITING_DEBT_CURRENCY":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona la moneda de la deuda usando los botones de abajo:*",
            reply_markup=INLINE_ERROR_KEYBOARD
        )
        return

    if state == "AWAITING_DEBT_AMOUNT":
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
            return
        
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
            await send_telegram_message(chat_id, mensaje_exito, reply_markup=INLINE_ERROR_KEYBOARD)
        except Exception as db_err:
            print(f"Error al guardar deuda: {db_err}")
            await send_telegram_message(chat_id, "❌ Error al guardar la deuda en la base de datos.", reply_markup=REPLY_KEYBOARD)
            USER_STATES.pop(chat_id, None)
        return
