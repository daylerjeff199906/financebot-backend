from datetime import datetime, timedelta
from constants import (
    ACCOUNT_TYPE_ICONS,
    TX_TYPE_LABELS,
    TX_TYPE_ICONS,
    SUPERADMIN_ID
)
from keyboards import (
    INLINE_ERROR_KEYBOARD,
    INLINE_CONFIRM_KEYBOARD,
    INLINE_TYPE_KEYBOARD,
    REPLY_KEYBOARD
)
from state_manager import USER_STATES
from utils import send_telegram_message, edit_telegram_message
from db import (
    get_user_accounts,
    get_user_transactions_current_month,
    get_user_transactions,
    create_user_account,
    insert_transaction,
    get_debt_by_id,
    update_debt,
    get_user_debts
)

# --- REUSABLE HELPERS ---

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
        
        tipo_label = TX_TYPE_LABELS.get(tx_type, tx_type.capitalize())
        
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
            await edit_telegram_message(chat_id, message_id, mensaje_exito, reply_markup=INLINE_ERROR_KEYBOARD)
        else:
            await send_telegram_message(chat_id, mensaje_exito, reply_markup=INLINE_ERROR_KEYBOARD)
            
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


# --- SUMMARY & MOVEMENTS ---

async def handle_resumen_menu(chat_id: int, user_uuid: str, edit_mode: bool = False, message_id: int = None):
    accounts = get_user_accounts(user_uuid)
    txs = get_user_transactions_current_month(user_uuid)
    
    bal_pen = 0.0
    bal_usd = 0.0
    acc_details = ""
    
    for acc in accounts:
        name = acc["name"]
        tipo = ACCOUNT_TYPE_ICONS.get(acc["type"], acc["type"].capitalize())
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
        
    # Obtener y calcular deudas para la comparativa
    debts = get_user_debts(user_uuid)
    debts_pay_pen = 0.0
    debts_pay_usd = 0.0
    debts_collect_pen = 0.0
    debts_collect_usd = 0.0
    
    for d in debts:
        if d.get("status") == "pendiente":
            curr = d.get("currency") or "PEN"
            rem = float(d.get("remaining_amount") or 0.0)
            dtype = d.get("type")
            
            if dtype == "por_pagar":
                if curr == "PEN":
                    debts_pay_pen += rem
                else:
                    debts_pay_usd += rem
            elif dtype == "por_cobrar":
                if curr == "PEN":
                    debts_collect_pen += rem
                else:
                    debts_collect_usd += rem
                    
    net_worth_pen = bal_pen - debts_pay_pen + debts_collect_pen
    net_worth_usd = bal_usd - debts_pay_usd + debts_collect_usd
    
    has_debts = (debts_pay_pen > 0 or debts_pay_usd > 0 or debts_collect_pen > 0 or debts_collect_usd > 0)
    has_usd = (bal_usd > 0 or debts_pay_usd > 0 or debts_collect_usd > 0 or any(a["currency"] == "USD" for a in accounts))
    
    debt_compare_str = ""
    if has_debts:
        debt_compare_str = (
            f"💸 *Comparativa con Deudas:*\n"
            f"▪️ Tú debes (Por Pagar): S/ {debts_pay_pen:.2f}"
        )
        if has_usd:
            debt_compare_str += f" | $ {debts_pay_usd:.2f}"
        debt_compare_str += f"\n▪️ Te deben (Por Cobrar): S/ {debts_collect_pen:.2f}"
        if has_usd:
            debt_compare_str += f" | $ {debts_collect_usd:.2f}"
            
        debt_compare_str += f"\n👉 *Saldo Neto Ajustado (Bruto - Debes + Cobras):*\n"
        debt_compare_str += f"   *S/ {net_worth_pen:.2f}*"
        if has_usd:
            debt_compare_str += f"  |  *$ {net_worth_usd:.2f}*"
        debt_compare_str += "\n\n"
    else:
        debt_compare_str = (
            f"💸 *Comparativa con Deudas:*\n"
            f"▪️ Sin deudas pendientes 🎉\n"
            f"👉 *Saldo Neto Ajustado:* *S/ {net_worth_pen:.2f}*"
        )
        if has_usd:
            debt_compare_str += f"  |  *$ {net_worth_usd:.2f}*"
        debt_compare_str += "\n\n"
        
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
        f"{debt_compare_str}"
        f"-----------------------------------\n"
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
    
    if edit_mode and message_id:
        await edit_telegram_message(chat_id, message_id, msg, reply_markup=keyboard)
    else:
        await send_telegram_message(chat_id, msg, reply_markup=keyboard)

async def handle_movimientos_menu(chat_id: int, user_uuid: str):
    txs = get_user_transactions(user_uuid, limit=5)
    if not txs:
        await send_telegram_message(chat_id, "🔄 *Últimos Movimientos:*\n\nNo tienes transacciones registradas aún.")
        return
    
    msg = "🔄 *Tus Últimos Movimientos:*\n\n"
    for t in txs:
        icono = TX_TYPE_ICONS.get(t["type"], t["type"].capitalize())
        concept = t["concept"] or "Sin concepto"
        currency = t["currency"] or "PEN"
        symbol = "S/" if currency == "PEN" else "$"
        amount = float(t["amount"])
        fecha = t.get("created_at", "")[:10] if t.get("created_at") else ""
        fecha_str = f" _({fecha})_" if fecha else ""
        msg += f"▪️ {icono}: *{symbol} {amount:.2f}* - {concept}{fecha_str}\n"
    
    await send_telegram_message(chat_id, msg, reply_markup=REPLY_KEYBOARD)


# --- MAIN CALLBACK DISPATCHER ---

async def handle_transactions_callbacks(chat_id: int, user_uuid: str, callback_data: str, message_id: int, callback_id: str, user_state: dict):
    if callback_data in ["reg_type:cancel", "confirm_type:cancel"]:
        USER_STATES.pop(chat_id, None)
        await edit_telegram_message(chat_id, message_id, "❌ *Registro cancelado.*", reply_markup=INLINE_ERROR_KEYBOARD)
        return

    if callback_data == "menu_resumen":
        await handle_resumen_menu(chat_id, user_uuid, edit_mode=True, message_id=message_id)
        return

    if callback_data == "menu_movimientos":
        await handle_movimientos_menu(chat_id, user_uuid)
        return

    if callback_data.startswith("reg_type:"):
        tx_type = callback_data.split(":")[1]
        USER_STATES[chat_id] = {
            "state": "AWAITING_AMOUNT",
            "type": tx_type
        }
        tipo_label = TX_TYPE_LABELS.get(tx_type, tx_type.capitalize())
        await edit_telegram_message(
            chat_id,
            message_id,
            f"💰 *Has seleccionado:* {tipo_label}\n\nPor favor, escribe el **monto** de la transacción (ejemplo: `25.50` o `100`):\n\n_(Puedes escribir /cancelar en cualquier momento)_"
        )
        return

    if callback_data.startswith("confirm_type:"):
        tx_type = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "CONFIRMING_PARSED_TX":
            await edit_telegram_message(chat_id, message_id, "⚠️ *Error:* Sesión de confirmación expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return

        user_state["type"] = tx_type
        await prompt_for_account_selection_or_proceed(chat_id, user_uuid, user_state, message_id)
        return

    if callback_data.startswith("tx_acc:"):
        account_id = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "AWAITING_TX_ACCOUNT":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
            
        user_state["account_id"] = account_id
        await prompt_for_date_selection(chat_id, user_state, message_id)
        return

    if callback_data.startswith("tx_date:"):
        date_type = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "AWAITING_TX_DATE":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
            
        if date_type == "today":
            user_state["date"] = datetime.now().strftime("%Y-%m-%d")
            await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
            
        elif date_type == "yesterday":
            yesterday = datetime.now() - timedelta(days=1)
            user_state["date"] = yesterday.strftime("%Y-%m-%d")
            await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
            
        elif date_type == "parsed":
            await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state, message_id)
            
        elif date_type == "custom":
            user_state["state"] = "AWAITING_TX_CUSTOM_DATE"
            USER_STATES[chat_id] = user_state
            await edit_telegram_message(
                chat_id,
                message_id,
                "✍️ *Ingresa la Fecha de la Operación*\n\nEscribe la fecha en formato **DD/MM/AAAA** (ejemplo: `15/05/2026` o `02/11/2025`):"
            )
        return

    if callback_data.startswith("tx_debt:"):
        debt_id = callback_data.split(":")[1]
        if not user_state or user_state.get("state") != "AWAITING_TX_DEBT":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
            
        if debt_id != "none":
            user_state["debt_id"] = debt_id
            
        await finish_transaction_registration(chat_id, user_uuid, user_state, message_id)
        return


# --- MAIN TEXT DISPATCHER ---

async def handle_transactions_states(chat_id: int, user_uuid: str, user_text: str, user_state: dict):
    state = user_state.get("state")

    if state == "CONFIRMING_PARSED_TX":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona una de las opciones del menú de abajo para guardar o cancelar la transacción:*",
            reply_markup=INLINE_CONFIRM_KEYBOARD
        )
        return

    if state == "AWAITING_TYPE":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona una opción usando los botones de abajo:*",
            reply_markup=INLINE_TYPE_KEYBOARD
        )
        return

    if state == "AWAITING_AMOUNT":
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
            return

        user_state["amount"] = amount
        user_state["state"] = "AWAITING_CONCEPT"
        
        tipo_label = TX_TYPE_LABELS.get(user_state["type"], user_state["type"].capitalize())

        await send_telegram_message(
            chat_id,
            f"💰 *Monto registrado:* S/ {amount:.2f}\n📂 *Categoría:* {tipo_label}\n\nAhora, escribe el **concepto** o descripción de la transacción (ejemplo: `Compras supermercado`, `Sueldo`):"
        )
        return

    if state == "AWAITING_CONCEPT":
        concept = user_text
        user_state["concept"] = concept
        user_state["currency"] = "PEN"  # Por defecto en el flujo manual simple es PEN
        
        await prompt_for_account_selection_or_proceed(chat_id, user_uuid, user_state)
        return

    if state == "AWAITING_TX_ACCOUNT":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona una cuenta usando los botones de abajo:*",
            reply_markup=INLINE_ERROR_KEYBOARD
        )
        return

    if state == "AWAITING_TX_DATE":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona una fecha usando los botones de abajo:*",
            reply_markup=INLINE_ERROR_KEYBOARD
        )
        return

    if state == "AWAITING_TX_CUSTOM_DATE":
        try:
            fecha_obj = datetime.strptime(user_text, "%d/%m/%Y")
            user_state["date"] = fecha_obj.strftime("%Y-%m-%d")
            await proceed_to_debt_check_or_finish(chat_id, user_uuid, user_state)
        except ValueError:
            await send_telegram_message(
                chat_id,
                "⚠️ *Fecha inválida.* Por favor, ingresa la fecha en formato **DD/MM/AAAA** (ejemplo: `15/05/2026`):"
            )
        return

    if state == "AWAITING_TX_DEBT":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona una deuda usando los botones de abajo o indica que no es para pagar deudas:*",
            reply_markup=INLINE_ERROR_KEYBOARD
        )
        return
