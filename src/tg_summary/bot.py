import logging
import re
from datetime import datetime, timezone

from dateutil.parser import parse as parse_date
from telegram import Bot
from telegram.constants import ParseMode

from tg_summary.config import (
    BOE_RSS_URL,
    DOG_RSS_URL,
    EU_FUNDING_RSS_URL,
    TELEGRAM_BOT_TOKEN,
)
from tg_summary.feed import compute_feed_hash, fetch_rss_entries, format_entries_for_prompt
from tg_summary.llm import analyze
from tg_summary.markdown_fix import split_markdown_smart
from tg_summary.recipients import load_recipients, build_system_prompt
from tg_summary.state import has_feed_changed, update_feed_state

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


def markdown_to_html(text: str) -> str:
    """Convert simple markdown to HTML for Telegram."""
    # Convert **bold** to <b>bold</b>
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    # Convert [text](url) to <a href="url">text</a>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


async def _send_telegram(bot: Bot, chat_id: str, text: str) -> None:
    """Send a message to Telegram using HTML format."""
    # Convert markdown to HTML
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
            # Fallback: send as plain text (strip HTML tags)
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


def _is_feed_stale(entries: list[dict]) -> bool:
    """Check if the feed entries are from a previous day (stale)."""
    today = datetime.now(timezone.utc).date()
    for entry in entries[:5]:
        pub = entry.get("published", "")
        if not pub:
            continue
        try:
            entry_date = parse_date(pub).date()
            if entry_date >= today:
                return False
        except (ValueError, OverflowError):
            continue
    # All checked entries are older than today (or unparseable)
    return True


NO_NEWS_MESSAGE = (
    "No hay novedades en los boletines de hoy. "
    "Si se publica algo relevante mas tarde, lo recibiras en el proximo envio. "
    "Buen dia!"
)


async def _process_feed(
    bot: Bot, chat_id: str, bulletin_key: str, name: str, rss_url: str, system_prompt: str
) -> bool:
    """Fetch an RSS feed, analyze it, and send the result to Telegram.

    Returns True if a summary was sent, False otherwise.
    """
    logger.info("Fetching %s RSS feed...", name)
    entries = fetch_rss_entries(rss_url)
    logger.info("%s: %d entries", name, len(entries))

    if not entries:
        logger.info("%s: no entries found, skipping", name)
        return False

    # Option B: check if feed content has changed since last run
    feed_hash = compute_feed_hash(entries)
    if not has_feed_changed(bulletin_key, feed_hash):
        logger.info("%s: feed unchanged (hash %s), skipping", name, feed_hash)
        return False

    # Option A: check if entries are stale (from a previous day)
    if _is_feed_stale(entries):
        logger.info("%s: feed entries are stale (not from today), skipping", name)
        # Still update state so we don't re-check stale content on next run
        update_feed_state(bulletin_key, feed_hash)
        return False

    entries_text = format_entries_for_prompt(entries)
    logger.info(
        "RSS snippet (%s, first 3):\n%s", name, format_entries_for_prompt(entries[:3])
    )

    logger.info("Analyzing %s with LLM...", name)
    analysis = await analyze(entries_text, system_prompt)

    message = f"**{name}**\n\n{analysis}"
    await _send_telegram(bot, chat_id, message)
    update_feed_state(bulletin_key, feed_hash)
    logger.info("%s summary sent to %s", name, chat_id)
    return True


async def send_summary() -> None:
    """Fetch DOG and BOE, analyze them for each recipient with custom prompts, and send."""
    recipients = load_recipients()
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for recipient in recipients:
        # Skip inactive users
        if not recipient.is_active:
            logger.info("Skipping inactive recipient %s", recipient.name)
            continue

        # Skip users who haven't completed setup
        if not recipient.setup_complete:
            logger.info("Skipping recipient %s - setup not complete", recipient.name)
            continue

        logger.info("Processing bulletins for %s...", recipient.name)

        any_sent = False
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

            try:
                sent = await _process_feed(
                    bot, recipient.chat_id, bulletin, bulletin_name, rss_url, system_prompt
                )
                if sent:
                    any_sent = True
            except Exception as e:
                logger.error(
                    "Failed to process %s for recipient %s: %s",
                    bulletin,
                    recipient.name,
                    e,
                )

        if not any_sent:
            logger.info("No bulletins had updates for %s, sending no-news message", recipient.name)
            try:
                await _send_telegram(bot, recipient.chat_id, NO_NEWS_MESSAGE)
            except Exception as e:
                logger.error("Failed to send no-news message to %s: %s", recipient.name, e)
