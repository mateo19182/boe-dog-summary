import re

# Characters that must be escaped in Telegram MarkdownV2
MARKDOWN_V2_ESCAPE_CHARS = r"_\*\[\]\(\)~`>#+\-=|\{\}\.!"


def escape_markdown_v2(text: str) -> str:
    """Escape all MarkdownV2 special characters to render text literally."""
    # Escape each special character with a backslash
    pattern = f"([{re.escape(MARKDOWN_V2_ESCAPE_CHARS)}])"
    return re.sub(pattern, r"\\\1", text)


def validate_markdown_v2(text: str) -> list[str]:
    """Return a list of errors in the Markdown text. Empty list means valid."""
    errors = []

    # Check for unbalanced bold markers **
    bold_count = text.count("**")
    if bold_count % 2 != 0:
        errors.append(f"unbalanced ** markers (count: {bold_count})")

    # Check for unbalanced italic markers __
    italic_count = text.count("__")
    if italic_count % 2 != 0:
        errors.append(f"unbalanced __ markers (count: {italic_count})")

    # Check for unbalanced inline code markers `
    code_count = text.count("`")
    if code_count % 2 != 0:
        errors.append(f"unbalanced ` markers (count: {code_count})")

    # Check for unbalanced spoiler markers ||
    spoiler_count = text.count("||")
    if spoiler_count % 2 != 0:
        errors.append(f"unbalanced || markers (count: {spoiler_count})")

    # Check for unbalanced strikethrough markers ~~
    strike_count = text.count("~~")
    if strike_count % 2 != 0:
        errors.append(f"unbalanced ~~ markers (count: {strike_count})")

    # Validate links: [text](url) pattern
    # Look for malformed links
    link_pattern = r"\[([^\]]*)\]\(([^\)]*)\)"
    for match in re.finditer(link_pattern, text):
        url = match.group(2)
        # Check if URL has unbalanced parentheses or brackets
        if url.count("(") != url.count(")"):
            errors.append(f"unbalanced parentheses in URL: {url[:50]}...")
        if url.count("[") != url.count("]"):
            errors.append(f"unbalanced brackets in URL: {url[:50]}...")

    # Check for lone brackets or parentheses that might indicate malformed Markdown
    open_brackets = text.count("[") - text.count("]")
    open_parens = text.count("(") - text.count(")")
    if open_brackets != 0:
        errors.append(f"unbalanced brackets: {open_brackets}")
    if open_parens != 0:
        errors.append(f"unbalanced parentheses: {open_parens}")

    return errors


def split_markdown_smart(text: str, max_length: int = 4096) -> list[str]:
    """
    Split Markdown text intelligently at content boundaries.

    Tries to split at:
    1. Complete list items (lines starting with - or numbered items)
    2. Paragraph breaks (double newlines)
    3. Single newlines

    Ensures each chunk has balanced Markdown markers.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Find best split point within max_length
        chunk, remaining = _find_split_point(remaining, max_length)
        chunks.append(chunk)

    return chunks


def _find_split_point(text: str, max_length: int) -> tuple[str, str]:
    """
    Find the best split point in text, preferring content boundaries.
    Returns (chunk, remaining) tuple.
    """
    search_end = min(max_length, len(text))

    # Priority 1: Split at double newline (paragraph break)
    for i in range(search_end - 1, 0, -1):
        if i < len(text) - 1 and text[i : i + 2] == "\n\n":
            return text[:i], text[i + 2 :].lstrip()

    # Priority 2: Split at single newline
    for i in range(search_end - 1, 0, -1):
        if text[i] == "\n":
            return text[:i], text[i + 1 :].lstrip()

    # Priority 3: Split at space (word boundary)
    for i in range(search_end - 1, max(search_end - 100, 0), -1):
        if text[i] == " ":
            return text[:i], text[i + 1 :].lstrip()

    # Priority 4: Hard split at max_length
    return text[:max_length], text[max_length:].lstrip()
