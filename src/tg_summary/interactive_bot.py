"""Interactive Telegram bot with user profile management."""

import logging
import re

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tg_summary.config import (
    BOE_RSS_URL,
    DEFAULT_INVITE_PASSWORD,
    DOG_RSS_URL,
    EU_FUNDING_RSS_URL,
    TELEGRAM_BOT_TOKEN,
)
from tg_summary.feed import fetch_rss_entries, format_entries_for_prompt
from tg_summary.llm import analyze
from tg_summary.markdown_fix import split_markdown_smart
from tg_summary.recipients import (
    Recipient,
    add_recipient,
    build_system_prompt,
    find_recipient_by_chat_id,
    load_invite_password,
    load_recipients,
    update_recipient,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096

BULLETIN_URLS = {
    "dog": DOG_RSS_URL,
    "boe": BOE_RSS_URL,
    "eu-funding": EU_FUNDING_RSS_URL,
}

BULLETIN_NAMES = {
    "dog": "DOG",
    "boe": "BOE",
    "eu-funding": "EU Funding & Tenders",
}

# Conversation states for wizard
(
    WIZARD_PROFILE,
    WIZARD_TOPICS_YES,
    WIZARD_TOPICS_NO,
    WIZARD_BULLETINS,
    WIZARD_CONFIRM,
) = range(5)


def markdown_to_html(text: str) -> str:
    """Convert simple markdown to HTML for Telegram."""
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


async def send_telegram_message(bot: Bot, chat_id: str, text: str) -> None:
    """Send a message to Telegram using HTML format."""
    html_text = markdown_to_html(text)
    chunks = split_markdown_smart(html_text, MAX_MESSAGE_LENGTH)

    for i, chunk in enumerate(chunks):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
            )
            logger.info("Sent chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        except Exception as e:
            logger.warning("Failed to send chunk %d with HTML: %s", i + 1, e)
            plain_text = re.sub(r"<[^>]+>", "", chunk)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=plain_text,
                )
                logger.info("Sent chunk %d/%d as plain text", i + 1, len(chunks))
            except Exception as e2:
                logger.error(
                    "Failed to send chunk %d even as plain text: %s", i + 1, e2
                )
                raise


async def process_single_bulletin(
    bot: Bot, chat_id: str, name: str, rss_url: str, system_prompt: str
) -> None:
    """Fetch an RSS feed, analyze it, and send the result to a single user."""
    logger.info("Fetching %s RSS feed for user %s...", name, chat_id)
    entries = fetch_rss_entries(rss_url)
    logger.info("%s: %d entries", name, len(entries))

    if not entries:
        await send_telegram_message(
            bot, chat_id, f"📭 No hay nuevas entradas en {name} hoy."
        )
        return

    entries_text = format_entries_for_prompt(entries)
    logger.info(
        "RSS snippet (%s, first 3):\n%s", name, format_entries_for_prompt(entries[:3])
    )

    logger.info("Analyzing %s with LLM...", name)
    analysis = await analyze(entries_text, system_prompt)

    await send_telegram_message(bot, chat_id, f"📰 <b>Resumen {name}</b>\n\n{analysis}")
    logger.info("%s summary sent to %s", name, chat_id)


# ==================== COMMANDS ====================


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with password authentication."""
    chat_id = str(update.effective_chat.id)
    args = context.args

    # Check if user is already registered
    existing = find_recipient_by_chat_id(chat_id)
    if existing:
        await update.message.reply_text(
            "👋 ¡Hola de nuevo! Ya estás registrado.\n\n"
            "Usa /setup para reconfigurar tu perfil o /help para ver todos los comandos."
        )
        return

    # Check password
    invite_password = load_invite_password() or DEFAULT_INVITE_PASSWORD

    if not args or args[0] != invite_password:
        await update.message.reply_text(
            "❌ Contraseña incorrecta o no proporcionada.\n\n"
            "Para registrarte, usa: /start <contraseña>\n\n"
            "Contacta al administrador si necesitas la contraseña de invitación."
        )
        return

    # Password correct - initialize user in wizard
    context.user_data["new_user"] = True
    context.user_data["profile_data"] = {
        "chat_id": chat_id,
        "name": update.effective_user.first_name or "Usuario",
        "bulletins": [],
        "profile": "",
        "relevance": {"yes": [], "no": []},
    }

    await update.message.reply_text(
        "🎉 ¡Bienvenido! Contraseña correcta.\n\n"
        "Vamos a configurar tu perfil para enviarte resúmenes personalizados.\n\n"
        "Paso 1/5: Describe tu perfil profesional o personal.\n"
        "Por ejemplo: 'Autónomo en Galicia con empresa tech de software deportivo'\n\n"
        "¿Cómo te describes?"
    )

    return WIZARD_PROFILE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message with all available commands."""
    help_text = """\
📋 <b>Comandos disponibles</b>

<b>Registro y configuración:</b>
/start &lt;contraseña&gt; - Registrarte con contraseña de invitación
/setup - Configurar/reconfigurar tu perfil completo (wizard)
/profile - Ver o editar tu descripción de perfil
/topics - Editar temas de interés y exclusión
/bulletins - Elegir qué boletines recibir (DOG, BOE, EU-funding)

<b>Control:</b>
/pause - Pausar/reanudar notificaciones diarias
/summary - Obtener resumen ahora mismo (on-demand)

<b>Ayuda:</b>
/help - Mostrar este mensaje de ayuda

<i>💡 Consejo: Puedes usar /setup en cualquier momento para rehacer tu configuración completa.</i>
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Launch the setup wizard."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if existing:
        # Pre-fill existing data
        context.user_data["new_user"] = False
        context.user_data["profile_data"] = {
            "chat_id": chat_id,
            "name": existing.name,
            "bulletins": existing.bulletins.copy(),
            "profile": existing.profile,
            "relevance": {
                "yes": existing.relevance.get("yes", []).copy(),
                "no": existing.relevance.get("no", []).copy(),
            },
        }
        await update.message.reply_text(
            "⚙️ <b>Configuración del perfil</b>\n\n"
            "Vamos a revisar tu perfil. Puedes modificar cualquier campo.\n\n"
            "Paso 1/5: Tu perfil actual:\n"
            f"<i>{existing.profile}</i>\n\n"
            "Escribe una nueva descripción o envía 'siguiente' para mantenerla."
        )
    else:
        # New user without proper /start - redirect
        await update.message.reply_text(
            "❌ Primero debes registrarte con /start <contraseña>\n\n"
            "Contacta al administrador para obtener la contraseña de invitación."
        )
        return ConversationHandler.END

    return WIZARD_PROFILE


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show current profile or enter edit mode."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await update.message.reply_text(
            "❌ No estás registrado. Usa /start <contraseña> para registrarte."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"👤 <b>Tu perfil actual:</b>\n\n"
        f"<i>{existing.profile}</i>\n\n"
        f"Escribe una nueva descripción para actualizarla, o 'cancelar' para salir:"
    )

    return WIZARD_PROFILE


async def topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show current topics or enter edit mode."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await update.message.reply_text(
            "❌ No estás registrado. Usa /start <contraseña> para registrarte."
        )
        return ConversationHandler.END

    yes_topics = "\n".join([f"  ✅ {t}" for t in existing.relevance.get("yes", [])])
    no_topics = "\n".join([f"  ❌ {t}" for t in existing.relevance.get("no", [])])

    await update.message.reply_text(
        f"📌 <b>Tus temas actuales:</b>\n\n"
        f"<b>SÍ relevantes:</b>\n{yes_topics}\n\n"
        f"<b>NO relevantes:</b>\n{no_topics}\n\n"
        "Paso 1/2: Escribe temas que te interesan (separados por comas), o 'cancelar':"
    )

    context.user_data["topics_mode"] = "yes"
    return WIZARD_TOPICS_YES


async def bulletins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show inline keyboard to toggle bulletins."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await update.message.reply_text(
            "❌ No estás registrado. Usa /start <contraseña> para registrarte."
        )
        return

    keyboard = []
    for bulletin in ["dog", "boe", "eu-funding"]:
        checked = "✅" if bulletin in existing.bulletins else "⬜"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{checked} {BULLETIN_NAMES[bulletin]}",
                    callback_data=f"toggle_{bulletin}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("✅ Guardar y salir", callback_data="bulletins_done")]
    )

    await update.message.reply_text(
        "📰 <b>Selecciona los boletines:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle is_active status."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await update.message.reply_text(
            "❌ No estás registrado. Usa /start <contraseña> para registrarte."
        )
        return

    new_status = not existing.is_active
    update_recipient(chat_id, {"is_active": new_status})

    status_text = "✅ Activadas" if new_status else "⏸️ Pausadas"
    await update.message.reply_text(
        f"{status_text} las notificaciones diarias.\n\n"
        f"Puedes usar /summary en cualquier momento para recibir un resumen bajo demanda."
    )


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send on-demand summary to user."""
    chat_id = str(update.effective_chat.id)
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await update.message.reply_text(
            "❌ No estás registrado. Usa /start <contraseña> para registrarte."
        )
        return

    if not existing.setup_complete:
        await update.message.reply_text(
            "⚠️ Completa tu configuración con /setup antes de solicitar resúmenes."
        )
        return

    await update.message.reply_text(
        "🔍 Generando resúmenes personalizados... Esto puede tardar unos segundos."
    )

    bot = context.bot

    for bulletin in existing.bulletins:
        if bulletin not in BULLETIN_URLS:
            continue

        rss_url = BULLETIN_URLS[bulletin]
        bulletin_name = BULLETIN_NAMES[bulletin]
        system_prompt = build_system_prompt(
            bulletin, existing.profile, existing.relevance
        )

        try:
            await process_single_bulletin(
                bot, chat_id, bulletin_name, rss_url, system_prompt
            )
        except Exception as e:
            logger.error("Failed to process %s for user %s: %s", bulletin, chat_id, e)
            await send_telegram_message(
                bot, chat_id, f"❌ Error al generar resumen de {bulletin_name}"
            )


# ==================== WIZARD HANDLERS ====================


async def wizard_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profile step in wizard."""
    text = update.message.text.strip()

    if text.lower() in ["cancelar", "cancel"]:
        await update.message.reply_text("❌ Configuración cancelada.")
        return ConversationHandler.END

    if text.lower() != "siguiente":
        context.user_data["profile_data"]["profile"] = text

    await update.message.reply_text(
        "Paso 2/5: ¿Qué temas te interesan?\n"
        "Escribe temas separados por comas.\n"
        "Ejemplo: 'subvenciones pymes, innovación, IA, deporte'"
    )

    return WIZARD_TOPICS_YES


async def wizard_topics_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle relevant topics (yes) step."""
    text = update.message.text.strip()

    if text.lower() in ["cancelar", "cancel"]:
        await update.message.reply_text("❌ Configuración cancelada.")
        return ConversationHandler.END

    topics = [t.strip() for t in text.split(",") if t.strip()]
    context.user_data["profile_data"]["relevance"]["yes"] = topics

    # If in topics_mode, save and exit
    if context.user_data.get("topics_mode") == "yes":
        await update.message.reply_text(
            "Paso 2/2: ¿Qué temas quieres EXCLUIR?\n"
            "Escribe temas separados por comas, o 'ninguno':"
        )
        context.user_data["topics_mode"] = "no"
        return WIZARD_TOPICS_NO

    await update.message.reply_text(
        "Paso 3/5: ¿Qué temas quieres EXCLUIR siempre?\n"
        "Escribe temas separados por comas, o 'ninguno':"
    )

    return WIZARD_TOPICS_NO


async def wizard_topics_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle excluded topics (no) step."""
    text = update.message.text.strip()

    if text.lower() in ["cancelar", "cancel"]:
        await update.message.reply_text("❌ Configuración cancelada.")
        return ConversationHandler.END

    if text.lower() == "ninguno":
        topics = []
    else:
        topics = [t.strip() for t in text.split(",") if t.strip()]

    context.user_data["profile_data"]["relevance"]["no"] = topics

    # If in topics_mode, save and exit
    if context.user_data.get("topics_mode") == "no":
        _save_profile_from_context(update, context)
        await update.message.reply_text(
            "✅ ¡Temas actualizados correctamente!\n\n"
            "Usa /bulletins para cambiar boletines o /summary para un resumen."
        )
        return ConversationHandler.END

    # Show bulletin selection keyboard
    keyboard = [
        [InlineKeyboardButton("⬜ DOG", callback_data="wizard_dog")],
        [InlineKeyboardButton("⬜ BOE", callback_data="wizard_boe")],
        [InlineKeyboardButton("⬜ EU Funding", callback_data="wizard_eu-funding")],
        [
            InlineKeyboardButton(
                "✅ Confirmar selección", callback_data="wizard_confirm_bulletins"
            )
        ],
    ]

    await update.message.reply_text(
        "Paso 4/5: Selecciona los boletines que quieres recibir:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return WIZARD_BULLETINS


async def wizard_bulletins_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle bulletin toggle in wizard."""
    query = update.callback_query
    await query.answer()

    data = query.data
    current_bulletins = context.user_data["profile_data"]["bulletins"]

    if data == "wizard_confirm_bulletins":
        if not current_bulletins:
            await query.edit_message_text(
                "⚠️ Debes seleccionar al menos un boletín.\n\n"
                "Paso 4/5: Selecciona los boletines:",
                reply_markup=query.message.reply_markup,
            )
            return WIZARD_BULLETINS

        # Show confirmation summary
        return await _show_wizard_confirmation(update, context)

    # Toggle bulletin
    bulletin = data.replace("wizard_", "")
    if bulletin in current_bulletins:
        current_bulletins.remove(bulletin)
    else:
        current_bulletins.append(bulletin)

    # Update keyboard
    keyboard = []
    for b in ["dog", "boe", "eu-funding"]:
        checked = "✅" if b in current_bulletins else "⬜"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{checked} {BULLETIN_NAMES[b]}", callback_data=f"wizard_{b}"
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                "✅ Confirmar selección", callback_data="wizard_confirm_bulletins"
            )
        ]
    )

    await query.edit_message_text(
        "Paso 4/5: Selecciona los boletines que quieres recibir:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return WIZARD_BULLETINS


async def _show_wizard_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Show final confirmation step."""
    data = context.user_data["profile_data"]

    yes_list = "\n".join([f"  ✅ {t}" for t in data["relevance"]["yes"]])
    no_list = "\n".join([f"  ❌ {t}" for t in data["relevance"]["no"]]) or "  (ninguno)"
    bulletins_list = ", ".join([BULLETIN_NAMES[b] for b in data["bulletins"]])

    summary = (
        f"📋 <b>Resumen de tu perfil:</b>\n\n"
        f"<b>Perfil:</b>\n{data['profile']}\n\n"
        f"<b>Temas de interés:</b>\n{yes_list}\n\n"
        f"<b>Temas excluidos:</b>\n{no_list}\n\n"
        f"<b>Boletines:</b> {bulletins_list}\n\n"
        f"¿Todo correcto?"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Guardar", callback_data="wizard_save"),
            InlineKeyboardButton("✏️ Editar", callback_data="wizard_edit"),
        ]
    ]

    if (
        isinstance(update.callback_query, type(update.callback_query))
        and update.callback_query
    ):
        await update.callback_query.edit_message_text(
            summary,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            summary,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

    return WIZARD_CONFIRM


async def wizard_confirm_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle final confirmation."""
    query = update.callback_query
    await query.answer()

    if query.data == "wizard_save":
        _save_profile_from_context(update, context)
        await query.edit_message_text(
            "✅ ¡Perfil guardado correctamente!\n\n"
            "Recibirás resúmenes diarios según tu configuración.\n"
            "Usa /summary para un resumen ahora mismo, o /help para más opciones."
        )
        return ConversationHandler.END

    elif query.data == "wizard_edit":
        # Restart wizard with current data
        await query.edit_message_text(
            "Volvamos a empezar. Paso 1/5: Describe tu perfil profesional:\n\n"
            f"<i>{context.user_data['profile_data']['profile']}</i>\n\n"
            "Escribe una nueva descripción o 'siguiente':",
            parse_mode=ParseMode.HTML,
        )
        return WIZARD_PROFILE

    return WIZARD_CONFIRM


def _save_profile_from_context(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Save profile data from context to recipients.json."""
    data = context.user_data["profile_data"]
    chat_id = str(update.effective_chat.id)

    existing = find_recipient_by_chat_id(chat_id)

    if existing:
        # Update existing
        updates = {
            "profile": data["profile"],
            "relevance": data["relevance"],
            "bulletins": data["bulletins"],
            "setup_complete": True,
        }
        update_recipient(chat_id, updates)
    else:
        # Create new
        recipient = Recipient(
            name=data["name"],
            chat_id=chat_id,
            bulletins=data["bulletins"],
            profile=data["profile"],
            relevance=data["relevance"],
            is_active=True,
            setup_complete=True,
        )
        add_recipient(recipient)


# ==================== CALLBACK HANDLERS ====================


async def bulletins_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle bulletin toggle callbacks."""
    query = update.callback_query
    await query.answer()

    chat_id = str(update.effective_chat.id)
    data = query.data

    if data == "bulletins_done":
        await query.edit_message_text("✅ Boletines actualizados correctamente.")
        return

    if not data.startswith("toggle_"):
        return

    bulletin = data.replace("toggle_", "")
    existing = find_recipient_by_chat_id(chat_id)

    if not existing:
        await query.edit_message_text("❌ Error: Usuario no encontrado.")
        return

    # Toggle
    bulletins = existing.bulletins.copy()
    if bulletin in bulletins:
        bulletins.remove(bulletin)
    else:
        bulletins.append(bulletin)

    update_recipient(chat_id, {"bulletins": bulletins})

    # Update keyboard
    keyboard = []
    for b in ["dog", "boe", "eu-funding"]:
        checked = "✅" if b in bulletins else "⬜"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{checked} {BULLETIN_NAMES[b]}", callback_data=f"toggle_{b}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("✅ Guardar y salir", callback_data="bulletins_done")]
    )

    await query.edit_message_text(
        "📰 <b>Selecciona los boletines:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


# ==================== APPLICATION SETUP ====================


def create_application() -> Application:
    """Create and configure the bot application."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation handler for wizard
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("setup", setup_command),
            CommandHandler("profile", profile_command),
            CommandHandler("topics", topics_command),
        ],
        states={
            WIZARD_PROFILE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_profile),
            ],
            WIZARD_TOPICS_YES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_topics_yes),
            ],
            WIZARD_TOPICS_NO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_topics_no),
            ],
            WIZARD_BULLETINS: [
                CallbackQueryHandler(wizard_bulletins_callback, pattern="^wizard_"),
            ],
            WIZARD_CONFIRM: [
                CallbackQueryHandler(wizard_confirm_callback, pattern="^wizard_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: u.message.reply_text("Cancelado."))
        ],
        per_message=True,  # Required for proper state tracking across messages
    )

    application.add_handler(conv_handler)

    # Other commands
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bulletins", bulletins_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("summary", summary_command))

    # Callbacks
    application.add_handler(
        CallbackQueryHandler(bulletins_callback, pattern="^(toggle_|bulletins_done)")
    )

    return application


async def run_bot() -> None:
    """Run the bot in polling mode."""
    application = create_application()

    logger.info("Starting bot in polling mode...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Run until manually stopped
    try:
        await application.updater.stop()
    except Exception:
        pass
