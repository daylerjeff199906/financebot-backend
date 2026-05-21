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

# Alias semántico para el menú de retorno
INLINE_BACK_START_KEYBOARD = INLINE_ERROR_KEYBOARD
