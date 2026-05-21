import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def get_user_by_telegram_id(telegram_id: int):
    # Busca al usuario en tu tabla users
    response = supabase.table("users").select("id").eq("telegram_id", telegram_id).execute()
    if len(response.data) > 0:
        return response.data[0]["id"]
    return None

def create_user_by_telegram_id(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None):
    # Intentamos crear el usuario con todos los datos disponibles
    payload = {"telegram_id": telegram_id}
    try:
        full_payload = {**payload}
        if username:
            full_payload["username"] = username
        if first_name:
            full_payload["first_name"] = first_name
        if last_name:
            full_payload["last_name"] = last_name
        
        response = supabase.table("users").insert(full_payload).execute()
        if len(response.data) > 0:
            return response.data[0]["id"]
    except Exception as e:
        print(f"Error al insertar con datos completos, reintentando solo con telegram_id: {e}")
        try:
            response = supabase.table("users").insert(payload).execute()
            if len(response.data) > 0:
                return response.data[0]["id"]
        except Exception as err:
            print(f"Error crítico al registrar usuario: {err}")
    return None

def get_user_default_account(user_uuid: str):
    response = supabase.table("accounts").select("id").eq("user_id", user_uuid).execute()
    if len(response.data) > 0:
        return response.data[0]["id"]
    return None

def create_default_account(user_uuid: str):
    payload = {
        "user_id": user_uuid,
        "name": "Efectivo",
        "type": "efectivo",
        "currency": "PEN",
        "initial_balance": 0.0,
        "current_balance": 0.0
    }
    response = supabase.table("accounts").insert(payload).execute()
    if len(response.data) > 0:
        return response.data[0]["id"]
    return None

def update_user_account(account_id: str, data: dict):
    response = supabase.table("accounts").update(data).eq("id", account_id).execute()
    return response.data

def update_account_balance(account_id: str, amount_change: float):
    # Fetch current balance
    res = supabase.table("accounts").select("current_balance").eq("id", account_id).execute()
    if len(res.data) > 0:
        current = float(res.data[0]["current_balance"] or 0.0)
        new_balance = current + amount_change
        supabase.table("accounts").update({"current_balance": new_balance}).eq("id", account_id).execute()

def insert_transaction(data: dict):
    # Si no se provee account_id, lo obtenemos o creamos por defecto
    if "account_id" not in data or not data["account_id"]:
        user_uuid = data.get("user_id")
        if user_uuid:
            account_id = get_user_default_account(user_uuid)
            if not account_id:
                account_id = create_default_account(user_uuid)
            data["account_id"] = account_id

    # Inserta directamente en la base de datos
    response = supabase.table("transactions").insert(data).execute()
    
    # Actualizar saldo de la cuenta automáticamente
    if len(response.data) > 0:
        tx = response.data[0]
        acc_id = tx.get("account_id")
        tx_type = tx.get("type")
        amount = float(tx.get("amount") or 0.0)
        
        if tx_type == "ingreso":
            update_account_balance(acc_id, amount)
        elif tx_type in ["gasto", "transferencia"]:
            update_account_balance(acc_id, -amount)
            
    return response.data

def get_user_accounts(user_uuid: str):
    response = supabase.table("accounts").select("*").eq("user_id", user_uuid).execute()
    return response.data

def create_user_account(data: dict):
    response = supabase.table("accounts").insert(data).execute()
    return response.data

def get_user_transactions(user_uuid: str, limit: int = 5):
    response = supabase.table("transactions").select("*").eq("user_id", user_uuid).order("created_at", desc=True).limit(limit).execute()
    return response.data

# --- NUEVAS FUNCIONES PARA DEUDAS ---
def get_user_debts(user_uuid: str):
    response = supabase.table("debts").select("*").eq("user_id", user_uuid).order("created_at", desc=True).execute()
    return response.data

def create_user_debt(data: dict):
    response = supabase.table("debts").insert(data).execute()
    return response.data

def get_debt_by_id(debt_id: str):
    response = supabase.table("debts").select("*").eq("id", debt_id).execute()
    if len(response.data) > 0:
        return response.data[0]
    return None

def update_debt(debt_id: str, data: dict):
    response = supabase.table("debts").update(data).eq("id", debt_id).execute()
    return response.data

# --- NUEVA FUNCIÓN PARA RESUMEN MENSUAL ---
def get_user_transactions_current_month(user_uuid: str):
    from datetime import datetime
    now = datetime.now()
    # Obtenemos primer día del mes actual en formato ISO
    start_date = datetime(now.year, now.month, 1, 0, 0, 0).isoformat()
    response = supabase.table("transactions").select("*").eq("user_id", user_uuid).gte("created_at", start_date).execute()
    return response.data


