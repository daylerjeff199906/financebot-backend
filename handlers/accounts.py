from constants import ACCOUNT_TYPE_ICONS
from keyboards import (
    INLINE_ACTYPE_KEYBOARD,
    INLINE_ACCURR_KEYBOARD,
    INLINE_ERROR_KEYBOARD,
    REPLY_KEYBOARD
)
from state_manager import USER_STATES
from utils import send_telegram_message, edit_telegram_message
from db import (
    get_user_accounts,
    create_user_account,
    update_user_account
)

async def handle_accounts_menu(chat_id: int, user_uuid: str):
    accounts = get_user_accounts(user_uuid)
    msg = "💳 *Tus Cuentas Financieras:*\n\n"
    msg += "Selecciona una cuenta de abajo para ver detalles o editarla, o crea una nueva:\n\n"
    
    inline_keyboard = []
    
    if not accounts:
        msg += "_No tienes ninguna cuenta registrada aún._"
    else:
        for acc in accounts:
            name = acc["name"]
            tipo = ACCOUNT_TYPE_ICONS.get(acc["type"], acc["type"].capitalize())
            curr = acc["currency"] or "PEN"
            sym = "S/" if curr == "PEN" else "$"
            bal = float(acc["current_balance"])
            msg += f"▪️ *{name}* ({tipo})\n   Saldo Actual: *{sym} {bal:.2f}*\n\n"
            inline_keyboard.append([{"text": f"⚙️ Configurar {name}", "callback_data": f"account_detail:{acc['id']}"}])
    
    inline_keyboard.append([{"text": "➕ Añadir Nueva Cuenta", "callback_data": "account_add:start"}])
    inline_keyboard.append([{"text": "🔙 Volver al Inicio", "callback_data": "menu_back_start"}])
    
    keyboard = {"inline_keyboard": inline_keyboard}
    await send_telegram_message(chat_id, msg, reply_markup=keyboard)

async def handle_accounts_callbacks(chat_id: int, user_uuid: str, callback_data: str, message_id: int, callback_id: str, user_state: dict):
    if callback_data == "menu_accounts":
        await handle_accounts_menu(chat_id, user_uuid)
        return

    if callback_data == "account_add:start":
        USER_STATES[chat_id] = {
            "state": "AWAITING_ACCOUNT_NAME"
        }
        await send_telegram_message(
            chat_id,
            "➕ *Añadir Nueva Cuenta*\n\nPor favor, escribe el **nombre** de la cuenta (ejemplo: `Billetera`, `Cuenta de Ahorros BCP`, `Tarjeta BBVA`):\n\n_(Puedes escribir Cancelar para abortar)_"
        )
        return

    if callback_data.startswith("account_detail:"):
        account_id = callback_data.split(":")[1]
        accounts = get_user_accounts(user_uuid)
        acc = next((a for a in accounts if a["id"] == account_id), None)
        if not acc:
            await send_telegram_message(chat_id, "⚠️ Cuenta no encontrada.")
            return
        
        name = acc["name"]
        tipo = ACCOUNT_TYPE_ICONS.get(acc["type"], acc["type"].capitalize())
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
        return

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
        return

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
        return

    if callback_data.startswith("actype:"):
        actype = callback_data.split(":")[1]
        if actype == "cancel":
            USER_STATES.pop(chat_id, None)
            await edit_telegram_message(chat_id, message_id, "❌ *Operación cancelada.*", reply_markup=INLINE_ERROR_KEYBOARD)
            return
        
        if not user_state or user_state.get("state") not in ["AWAITING_ACCOUNT_TYPE", "AWAITING_EDIT_ACCOUNT_TYPE"]:
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada o inválida.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
        
        if user_state.get("state") == "AWAITING_EDIT_ACCOUNT_TYPE":
            account_id = user_state["account_id"]
            try:
                update_user_account(account_id, {"type": actype})
                tipo_label = ACCOUNT_TYPE_ICONS.get(actype, actype.capitalize())
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
            return
        
        # Flujo clásico de creación
        user_state["type"] = actype
        user_state["state"] = "AWAITING_ACCOUNT_CURRENCY"
        
        await edit_telegram_message(
            chat_id,
            message_id,
            "💱 *Selecciona la moneda de la cuenta:*",
            reply_markup=INLINE_ACCURR_KEYBOARD
        )
        return

    if callback_data.startswith("accurr:"):
        accurr = callback_data.split(":")[1]
        if accurr == "cancel":
            USER_STATES.pop(chat_id, None)
            await edit_telegram_message(chat_id, message_id, "❌ *Creación de cuenta cancelada.*", reply_markup=INLINE_ERROR_KEYBOARD)
            return
        
        if not user_state or user_state.get("state") != "AWAITING_ACCOUNT_CURRENCY":
            await edit_telegram_message(chat_id, message_id, "⚠️ Sesión expirada.", reply_markup=INLINE_ERROR_KEYBOARD)
            return
        
        user_state["currency"] = accurr
        user_state["state"] = "AWAITING_ACCOUNT_BALANCE"
        
        await edit_telegram_message(
            chat_id,
            message_id,
            f"💰 *Has seleccionado:* {accurr}\n\nPor favor, escribe el **saldo inicial** de la cuenta (ejemplo: `0` o `150.50`):"
        )
        return

async def handle_accounts_states(chat_id: int, user_uuid: str, user_text: str, user_state: dict):
    state = user_state.get("state")

    if state == "AWAITING_ACCOUNT_NAME":
        user_state["name"] = user_text
        user_state["state"] = "AWAITING_ACCOUNT_TYPE"
        
        await send_telegram_message(
            chat_id,
            f"📂 *Nombre de cuenta:* {user_text}\n\nSelecciona el **tipo de cuenta** usando los botones de abajo:",
            reply_markup=INLINE_ACTYPE_KEYBOARD
        )
        return

    if state == "AWAITING_ACCOUNT_TYPE":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona el tipo de cuenta usando los botones de abajo:*",
            reply_markup=INLINE_ACTYPE_KEYBOARD
        )
        return

    if state == "AWAITING_ACCOUNT_CURRENCY":
        await send_telegram_message(
            chat_id,
            "⚠️ *Por favor, selecciona la moneda de la cuenta usando los botones de abajo:*",
            reply_markup=INLINE_ACCURR_KEYBOARD
        )
        return

    if state == "AWAITING_ACCOUNT_BALANCE":
        clean_bal = user_text.replace("S/", "").replace("$", "").replace(",", ".").replace(" ", "")
        try:
            balance = float(clean_bal)
        except ValueError:
            await send_telegram_message(
                chat_id,
                "⚠️ *Saldo inválido.* Por favor, ingresa solo números (ejemplo: `0` o `150.50`):",
                reply_markup=INLINE_ERROR_KEYBOARD
            )
            return
        
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
            return
        
        USER_STATES.pop(chat_id, None)
        
        type_label = ACCOUNT_TYPE_ICONS.get(actype, actype.capitalize())
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
        
        await send_telegram_message(chat_id, mensaje_exito, reply_markup=INLINE_ERROR_KEYBOARD)
        return

    if state == "AWAITING_EDIT_ACCOUNT_NAME":
        account_id = user_state["account_id"]
        new_name = user_text
        try:
            update_user_account(account_id, {"name": new_name})
            USER_STATES.pop(chat_id, None)
            await send_telegram_message(
                chat_id,
                f"✅ *¡Nombre de Cuenta Actualizado!*\n\nEl nombre ha sido cambiado a: *{new_name}*",
                reply_markup=INLINE_ERROR_KEYBOARD
            )
        except Exception as err:
            print(f"Error al actualizar nombre de cuenta: {err}")
            await send_telegram_message(chat_id, "❌ Error al actualizar el nombre de la cuenta.", reply_markup=REPLY_KEYBOARD)
            USER_STATES.pop(chat_id, None)
        return
