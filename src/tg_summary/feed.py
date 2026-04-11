import hashlib

import feedparser
import httpx


def fetch_rss_entries(url: str) -> list[dict]:
    """Fetch RSS entries from a URL and return them as a list of dicts."""
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    feed = feedparser.parse(response.text)

    entries = []
    for entry in feed.entries:
        entries.append(
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
            }
        )
    return entries


def compute_feed_hash(entries: list[dict]) -> str:
    """Compute a hash of the feed entries to detect changes."""
    content = "|".join(e.get("link", "") or e.get("title", "") for e in entries)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def format_entries_for_prompt(entries: list[dict]) -> str:
    """Format RSS entries into a text block for the LLM prompt."""
    if not entries:
        return "No se encontraron publicaciones hoy."

    lines = []
    for i, entry in enumerate(entries, 1):
        lines.append(f"[{i}] {entry['title']}")
        if entry["summary"]:
            lines.append(f"    {entry['summary']}")
        if entry["link"]:
            lines.append(f"    URL: {entry['link']}")
        lines.append("")
    return "\n".join(lines)


def fetch_feed(url: str) -> tuple[list[dict], str]:
    """Fetch RSS entries from a URL and compute their hash.

    Returns (entries, feed_hash) tuple.
    """
    entries = fetch_rss_entries(url)
    feed_hash = compute_feed_hash(entries)
    return entries, feed_hash
