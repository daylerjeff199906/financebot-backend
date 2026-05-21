import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Inicializamos el cliente de Google GenAI
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
Eres un asistente financiero. El usuario te enviará un mensaje de texto sobre un ingreso o gasto.
Tu tarea es extraer la información y devolver ÚNICAMENTE un objeto JSON válido con la siguiente estructura, sin formato Markdown ni texto adicional:
{
  "type": "gasto" | "ingreso" | "transferencia",
  "amount": número decimal (solo el número, positivo),
  "concept": "breve descripción del gasto/ingreso",
  "currency": "PEN" | "USD",
  "date": "YYYY-MM-DD" o null si no se menciona específicamente una fecha (ej. si dice 'ayer', calcula la fecha de ayer; si dice 'el 12 de mayo', calcula esa fecha en el año actual; de lo contrario null)
}
Si falta información, infiérela lógicamente (ej. si dice 'menú', es gasto en PEN).
"""

async def parse_finance_text(text: str) -> dict:
    try:
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{SYSTEM_PROMPT}\n\nMensaje del usuario: {text}"
        )
        # Limpiamos posibles tildes o backticks de markdown que a veces Gemini incluye
        raw_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_json)
    except Exception as e:
        print(f"Error procesando IA: {e}")
        return None

