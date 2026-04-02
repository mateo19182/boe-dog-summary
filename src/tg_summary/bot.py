import logging

from telegram import Bot
from telegram.constants import ParseMode

from tg_summary.config import (
    BOE_RSS_URL,
    DOG_RSS_URL,
    TELEGRAM_BOT_TOKEN,
)
from tg_summary.feed import fetch_rss_entries, format_entries_for_prompt
from tg_summary.llm import analyze
from tg_summary.markdown_fix import split_markdown_smart
from tg_summary.recipients import load_recipients, build_system_prompt

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096

BULLETIN_URLS = {
    "dog": DOG_RSS_URL,
    "boe": BOE_RSS_URL,
}

BULLETIN_NAMES = {
    "dog": "DOG",
    "boe": "BOE",
}


async def _send_telegram(bot: Bot, chat_id: str, text: str) -> None:
    """Send a message to Telegram, splitting intelligently at content boundaries."""
    chunks = split_markdown_smart(text, MAX_MESSAGE_LENGTH)

    for i, chunk in enumerate(chunks):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            logger.info("Sent chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        except Exception as e:
            logger.warning("Failed to send chunk %d with MarkdownV2: %s", i + 1, e)
            # Fallback: send as plain text (strip markdown)
            plain_text = chunk.replace("**", "").replace("__", "").replace("`", "")
            plain_text = plain_text.replace("[", "").replace("]", "")
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


async def _process_feed(
    bot: Bot, chat_id: str, name: str, rss_url: str, system_prompt: str
) -> None:
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

    await _send_telegram(bot, chat_id, analysis)
    logger.info("%s summary sent to %s", name, chat_id)


async def send_summary() -> None:
    """Fetch DOG and BOE, analyze them for each recipient with custom prompts, and send."""
    recipients = load_recipients()
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for recipient in recipients:
        logger.info("Processing bulletins for %s...", recipient.name)

        for bulletin in recipient.bulletins:
            if bulletin not in BULLETIN_URLS:
                logger.warning(
                    "Unknown bulletin '%s' for recipient %s", bulletin, recipient.name
                )
                continue

            rss_url = BULLETIN_URLS[bulletin]
            bulletin_name = BULLETIN_NAMES[bulletin]
            system_prompt = build_system_prompt(
                bulletin, recipient.profile, recipient.relevance
            )

            await _process_feed(
                bot, recipient.chat_id, bulletin_name, rss_url, system_prompt
            )
