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

