"""Track last-seen feed state to avoid sending duplicate summaries."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent.parent / "feed_state.json"


def load_state() -> dict:
    """Load the feed state from disk."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load feed state: %s", e)
        return {}


def save_state(state: dict) -> None:
    """Save the feed state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def has_feed_changed(bulletin: str, feed_hash: str) -> bool:
    """Check if a feed has changed since the last run."""
    state = load_state()
    last_hash = state.get(bulletin, {}).get("hash")
    return last_hash != feed_hash


def update_feed_state(bulletin: str, feed_hash: str) -> None:
    """Record that we've processed a feed with the given hash."""
    state = load_state()
    state[bulletin] = {"hash": feed_hash}
    save_state(state)
