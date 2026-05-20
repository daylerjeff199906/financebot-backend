# 🪙 FinanceBot Backend - Guía de Inicio Rápido

Este repositorio contiene el backend desarrollado en **FastAPI** para tu asistente financiero personal de Telegram. Integra la base de datos **Supabase** para persistencia de datos y la IA de **Google Gemini** para procesamiento inteligente de mensajes de texto en lenguaje natural.

---

## 🛠️ Requisitos Previos

Asegúrate de contar con lo siguiente en tu sistema:
1. **Python 3.10+** instalado.
2. Un bot de Telegram creado a través de [@BotFather](https://t.me/BotFather) (para obtener el Token).
3. Una base de datos activa en Supabase.
4. Cliente SSH habilitado en tu terminal (para abrir el túnel público gratuito).

---

## 📂 Configuración Inicial

El backend utiliza un archivo `.env` para almacenar las credenciales sensibles. Asegúrate de que tu archivo `d:\FREELANCE\financebot-backend\.env` contenga la siguiente estructura con tus datos reales:

```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
SUPABASE_URL=tu_url_de_supabase
SUPABASE_KEY=tu_clave_de_supabase
GEMINI_API_KEY=tu_clave_api_de_gemini
SUPERADMIN_TELEGRAM_ID=tu_id_de_telegram
TELEGRAM_WEBHOOK_SECRET=un_secreto_aleatorio_creado_por_ti
```

---

## 🚀 Pasos para Levantar y Ejecutar el Sistema

Sigue estos 3 simples pasos para poner en marcha el bot y que responda tus mensajes en tiempo real:

### 1️⃣ Levantar el Servidor Backend (FastAPI)
Ejecuta el servidor local sobre el puerto `8000` utilizando el entorno virtual provisto:

En PowerShell / CMD:
```powershell
.\venv\Scripts\uvicorn.exe main:app --port 8000
```
*El servidor estará escuchando localmente en `http://localhost:8000`.*

---

### 2️⃣ Exponer el Servidor a Internet (Túnel Pinggy)
Telegram requiere una dirección HTTPS pública para poder enviarte los mensajes del chat a tu computadora. Abrimos un túnel público seguro y gratuito usando **Pinggy** (no requiere instalar nada):

Abre una **nueva ventana de terminal** y ejecuta:
```powershell
ssh -T -o StrictHostKeyChecking=no -p 443 -R0:localhost:8000 a.pinggy.io
```

Una vez conectado, verás en la consola unas líneas parecidas a estas:
```text
http://xxxxx-148-227-77-139.run.pinggy-free.link
https://xxxxx-148-227-77-139.run.pinggy-free.link
```
> [!IMPORTANT]
> Copia la dirección que empieza con **`https://`**. Esta es tu dirección pública temporal de hoy.

---

### 3️⃣ Registrar el Webhook en Telegram
Para que Telegram sepa a dónde enviar los chats, debes actualizar el webhook con tu nueva URL pública:

1. Abre el archivo `set_webhook.py` y edita la línea de la variable `PUBLIC_URL` con tu URL copiada en el paso anterior:
   ```python
   PUBLIC_URL = "https://xxxxx-148-227-77-139.run.pinggy-free.link"
   ```
2. Ejecuta el script de configuración en tu terminal:
   ```powershell
   .\venv\Scripts\python.exe set_webhook.py
   ```
3. Si todo salió bien, verás una respuesta de Telegram confirmando el registro:
   ```json
   {"ok": true, "result": true, "description": "Webhook was set"}
   ```

---

## 📱 ¿Cómo probar el Bot en Telegram?

¡Una vez concluidos los 3 pasos, tu bot estará en línea y listo!
Abre el chat de tu bot en Telegram y prueba los siguientes comandos:

*   `/start` o `Iniciar`: Despliega el menú principal interactivo con botones integrados.
*   `💳 Mis Cuentas`: Lista todas tus cuentas financieras en tiempo real y ofrece un botón interactivo para **añadir nuevas cuentas** con flujo guiado de nombre, tipo (Efectivo, Banco, Tarjeta) y saldo inicial.
*   `🔄 Últimos Movimientos`: Muestra el historial reciente de tus últimas 5 transacciones de forma muy visual y detallada.
*   `📝 Registrar Transacción`: Inicia el flujo guiado estructurado para ingresar gastos e ingresos sin IA.
*   **Mensajes de texto libre (IA Gemini)**: Escribe de forma natural (ej: *"gasté 45.50 soles en pizza"*) y el bot usará inteligencia artificial para detectar y sugerirte guardar la transacción de forma inmediata.

---

## 🛑 Detener los Servidores
Para apagar los servidores, simplemente presiona **`CTRL + C`** en cada una de las terminales abiertas donde se están ejecutando Uvicorn y el túnel SSH de Pinggy.
