import logging

from telegram import Bot
from telegram.constants import ParseMode

from tg_summary.config import (
    BOE_RSS_URL,
    BOE_SYSTEM_PROMPT,
    DOG_RSS_URL,
    DOG_SYSTEM_PROMPT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from tg_summary.feed import fetch_rss_entries, format_entries_for_prompt
from tg_summary.html_fix import sanitize_telegram_html, validate_telegram_html
from tg_summary.llm import analyze

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
MAX_LLM_RETRIES = 2


async def _send_telegram(bot: Bot, text: str) -> None:
    """Send a message to Telegram, splitting if needed."""
    chunks = [
        text[i : i + MAX_MESSAGE_LENGTH]
        for i in range(0, len(text), MAX_MESSAGE_LENGTH)
    ]
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk)


async def _process_feed(bot: Bot, name: str, rss_url: str, system_prompt: str) -> None:
    """Fetch an RSS feed, analyze it, and send the result to Telegram."""
    logger.info("Fetching %s RSS feed...", name)
    entries = fetch_rss_entries(rss_url)
    logger.info("%s: %d entries", name, len(entries))

    entries_text = format_entries_for_prompt(entries)
    logger.info(
        "RSS snippet (%s, first 3):\n%s", name, format_entries_for_prompt(entries[:3])
    )

    logger.info("Analyzing %s with LLM...", name)
    analysis = await analyze(entries_text, system_prompt)

    # Validate and fix HTML
    errors = validate_telegram_html(analysis)
    if errors:
        logger.warning("%s: invalid HTML from LLM: %s", name, errors)
        analysis = sanitize_telegram_html(analysis)
        errors = validate_telegram_html(analysis)
        if errors:
            logger.warning("%s: still invalid after sanitize, retrying LLM...", name)
            for attempt in range(1, MAX_LLM_RETRIES + 1):
                analysis = await analyze(entries_text, system_prompt)
                analysis = sanitize_telegram_html(analysis)
                errors = validate_telegram_html(analysis)
                if not errors:
                    logger.info("%s: retry %d produced valid HTML", name, attempt)
                    break
                logger.warning("%s: retry %d still invalid: %s", name, attempt, errors)
            else:
                logger.warning(
                    "%s: giving up on valid HTML, sending as plain text", name
                )

    await _send_telegram(bot, analysis)
    logger.info("%s summary sent", name)


async def send_summary() -> None:
    """Fetch DOG and BOE, analyze both, and send as separate messages."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    await _process_feed(bot, "DOG", DOG_RSS_URL, DOG_SYSTEM_PROMPT)
    await _process_feed(bot, "BOE", BOE_RSS_URL, BOE_SYSTEM_PROMPT)
