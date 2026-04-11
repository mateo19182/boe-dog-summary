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
from tg_summary.feed import fetch_feed, format_entries_for_prompt
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
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


async def _send_telegram(bot: Bot, chat_id: str, text: str) -> None:
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
    return True


NO_NEWS_MESSAGE = (
    "No hay novedades en los boletines de hoy. "
    "Si se publica algo relevante mas tarde, lo recibiras en el proximo envio. "
    "Buen dia!"
)


def prefetch_feeds() -> dict[str, tuple[list[dict], str]]:
    """Fetch all feeds once and return {bulletin: (entries, hash)}."""
    results = {}
    for bulletin, url in BULLETIN_URLS.items():
        name = BULLETIN_NAMES[bulletin]
        logger.info("Fetching %s RSS feed...", name)
        entries, feed_hash = fetch_feed(url)
        logger.info("%s: %d entries, hash: %s", name, len(entries), feed_hash)
        results[bulletin] = (entries, feed_hash)
    return results


async def send_summary() -> None:
    """Fetch feeds once, analyze for each recipient with custom prompts, and send.

    Strategy:
    - Prefetch all feeds globally (each feed fetched only once)
    - For each bulletin, check if hash changed
    - If changed: send personalized analysis to ALL recipients who want that bulletin
    - After all recipients processed, update global state for that bulletin
    - If no feeds changed, send no-news message to everyone
    """
    recipients = load_recipients()
    active_recipients = [r for r in recipients if r.is_active and r.setup_complete]
    if not active_recipients:
        logger.info("No active recipients, skipping")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    prefetched = prefetch_feeds()

    any_sent = False
    for bulletin in BULLETIN_URLS:
        entries, feed_hash = prefetched[bulletin]
        name = BULLETIN_NAMES[bulletin]

        if not entries:
            logger.info("%s: no entries found, skipping", name)
            continue

        if not has_feed_changed(bulletin, feed_hash):
            logger.info("%s: feed unchanged (hash %s), skipping", name, feed_hash)
            continue

        if _is_feed_stale(entries):
            logger.info("%s: feed entries are stale (not from today), skipping", name)
            update_feed_state(bulletin, feed_hash)
            continue

        logger.info(
            "RSS snippet (%s, first 3):\n%s",
            name,
            format_entries_for_prompt(entries[:3]),
        )

        recipients_for_bulletin = [
            r for r in active_recipients if bulletin in r.bulletins
        ]
        if not recipients_for_bulletin:
            logger.info("No recipients want %s, skipping", name)
            continue

        for recipient in recipients_for_bulletin:
            system_prompt = build_system_prompt(
                bulletin, recipient.profile, recipient.relevance
            )
            entries_text = format_entries_for_prompt(entries)

            logger.info("Analyzing %s with LLM for %s...", name, recipient.name)
            try:
                analysis = await analyze(entries_text, system_prompt)
                message = f"**{name}**\n\n{analysis}"
                await _send_telegram(bot, recipient.chat_id, message)
                logger.info("%s summary sent to %s", name, recipient.name)
                any_sent = True
            except Exception as e:
                logger.error(
                    "Failed to send %s to %s: %s",
                    bulletin,
                    recipient.name,
                    e,
                )

        update_feed_state(bulletin, feed_hash)

    if not any_sent:
        logger.info("No bulletins had updates, sending no-news message to all")
        for recipient in active_recipients:
            try:
                await _send_telegram(bot, recipient.chat_id, NO_NEWS_MESSAGE)
            except Exception as e:
                logger.error(
                    "Failed to send no-news message to %s: %s",
                    recipient.name,
                    e,
                )
