import re
from html.parser import HTMLParser

# Tags supported by Telegram's HTML parse mode
ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "tg-spoiler", "tg-emoji", "blockquote",
}


class _TelegramHTMLValidator(HTMLParser):
    """Check if HTML only uses Telegram-supported tags and is well-formed."""

    def __init__(self):
        super().__init__()
        self.errors: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"unsupported tag <{tag}>")
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        else:
            self.errors.append(f"mismatched </{tag}>")

    def close(self) -> None:
        super().close()
        for tag in self._stack:
            self.errors.append(f"unclosed <{tag}>")


def validate_telegram_html(text: str) -> list[str]:
    """Return a list of errors found in the HTML. Empty list means valid."""
    parser = _TelegramHTMLValidator()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:
        return [f"parse error: {e}"]
    return parser.errors


def sanitize_telegram_html(text: str) -> str:
    """Best-effort fix of common HTML issues for Telegram."""
    # Remove unsupported tags (keep their content)
    def _strip_tag(m: re.Match) -> str:
        tag = m.group(1).split()[0].strip("/").lower()
        if tag in ALLOWED_TAGS:
            return m.group(0)
        return ""

    text = re.sub(r"<(/?\w[^>]*)>", _strip_tag, text)

    # Close unclosed tags
    stack: list[str] = []
    for m in re.finditer(r"<(/?)(\w+)[^>]*>", text):
        is_close, tag = m.group(1), m.group(2).lower()
        if tag not in ALLOWED_TAGS:
            continue
        if not is_close:
            stack.append(tag)
        elif stack and stack[-1] == tag:
            stack.pop()

    for tag in reversed(stack):
        text += f"</{tag}>"

    return text
