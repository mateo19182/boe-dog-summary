# BOE-DOG Summary Bot

Daily Telegram bot that fetches and summarizes official bulletins (DOG and BOE) using AI analysis.

## Overview

This bot automatically fetches RSS feeds from:
- **DOG** (Diario Oficial de Galicia) - Galicia's official bulletin
- **BOE** (Boletín Oficial del Estado) - Spain's official state bulletin

It uses LLM (via OpenRouter) to analyze entries and extract only relevant information based on configurable criteria, then sends formatted summaries to Telegram.

## Features

- Fetches RSS feeds from DOG and BOE
- AI-powered content analysis using OpenRouter (Gemini model by default)
- Filters entries by relevance profile (autónomos, tech companies, I+D, etc.)
- Sends formatted HTML messages to Telegram
- Automatic HTML validation and sanitization
- Message chunking for long summaries
- Retry logic for invalid LLM outputs

## Installation

```bash
# Clone the repository
git clone https://github.com/mateo19182/boe-dog-summary.git
cd boe-dog-summary

# Install dependencies (using uv)
uv sync

# Or using pip
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID where messages will be sent |
| `OPENROUTER_API_KEY` | API key from openrouter.ai |
| `OPENROUTER_MODEL` | (Optional) Model to use, defaults to `google/gemini-2.5-flash-preview` |

### Getting Your Telegram Chat ID

1. Create a bot via @BotFather and get your token
2. Send a message to your bot
3. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Look for the `chat.id` value

## Usage

### Running manually

```bash
# Using uv
uv run boe-dog-summary

# Or after pip install
boe-dog-summary
```

### Setting up a cron job (Linux/Mac)

Run daily at 9 AM:

```bash
0 9 * * * cd /path/to/boe-dog-summary && uv run boe-dog-summary >> /var/log/boe-dog-summary.log 2>&1
```

## Project Structure

```
boe-dog-summary/
├── src/
│   └── tg_summary/
│       ├── __init__.py      # Package initialization
│       ├── main.py          # Entry point
│       ├── bot.py           # Telegram bot logic
│       ├── config.py        # Configuration and prompts
│       ├── llm.py           # OpenRouter API integration
│       ├── feed.py          # RSS feed fetching
│       └── markdown_fix.py  # Markdown validation/smart splitting
├── .env.example             # Environment variables template
├── .gitignore              # Git ignore patterns
├── pyproject.toml          # Project configuration
└── README.md               # This file
```

## Customization

Edit `src/tg_summary/config.py` to customize:

- **Profile**: Change the target audience description
- **Relevance criteria**: Define what entries to include/exclude
- **Output format**: Modify the LLM output structure
- **RSS URLs**: Point to different feeds if needed

## Dependencies

- `feedparser` - RSS feed parsing
- `httpx` - Async HTTP client
- `python-telegram-bot` - Telegram API
- `python-dotenv` - Environment variable management

## License

MIT License
