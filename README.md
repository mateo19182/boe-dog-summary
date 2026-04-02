# BOE-DOG Summary Bot

Telegram bot that fetches and summarizes official bulletins (DOG, BOE, EU Funding) using AI analysis. Now with interactive user profiles!

## Overview

This bot automatically fetches RSS feeds from:
- **DOG** (Diario Oficial de Galicia) - Galicia's official bulletin
- **BOE** (Boletín Oficial del Estado) - Spain's official state bulletin  
- **EU Funding & Tenders** - European Union funding opportunities

It uses LLM (via OpenRouter) to analyze entries and extract only relevant information based on configurable criteria, then sends formatted summaries to Telegram.

## Features

### Core Features
- 🤖 **AI-powered content analysis** using OpenRouter (Gemini model by default)
- 📰 **Multiple official bulletins** (DOG, BOE, EU Funding)
- 🎯 **Personalized filtering** based on user profiles and topics
- 📝 **Smart formatting** with HTML/Markdown support
- ✂️ **Message chunking** for long summaries

### New Interactive Features
- 🔐 **Invite-based registration** - Users join with a password
- 👤 **Self-service profiles** - Users configure their own settings
- 🎛️ **Interactive wizard** - 5-step setup for new users
- ⚙️ **Easy management** commands:
  - `/setup` - Re-run full configuration wizard
  - `/profile` - Edit profile description
  - `/topics` - Change relevant/excluded topics
  - `/bulletins` - Toggle which bulletins to receive
  - `/pause` - Pause/resume daily notifications
  - `/summary` - Get instant summary on-demand
- 📊 **Per-user configuration** stored in JSON

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
| `AINHOA_CHAT_ID` | (Optional) Second user's chat ID |
| `OPENROUTER_API_KEY` | API key from openrouter.ai |
| `OPENROUTER_MODEL` | (Optional) Model to use, defaults to `google/gemini-2.5-flash-preview` |
| `INVITE_PASSWORD` | (Optional) Override default invite password |

### Getting Your Telegram Chat ID

1. Create a bot via @BotFather and get your token
2. Send a message to your bot
3. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Look for the `chat.id` value

### Setting the Invite Password

Edit `recipients.json` and set your invite password:

```json
{
  "invite_password": "YOUR_SECRET_PASSWORD",
  "recipients": [...]
}
```

## Usage

### Running in Bot Mode (Interactive)

Start the bot to handle user interactions:

```bash
# Using uv
uv run boe-dog-summary

# Or after pip install
boe-dog-summary

# Explicit mode
boe-dog-summary --mode bot
```

### Running in Cron Mode (Daily Summaries)

For automated daily summaries, use cron mode:

```bash
# Using uv
uv run boe-dog-summary --mode cron

# Or after pip install
boe-dog-summary --mode cron
```

### Setting up a Cron Job (Linux/Mac)

Run daily at 9 AM:

```bash
0 9 * * * cd /path/to/boe-dog-summary && uv run boe-dog-summary --mode cron >> /var/log/boe-dog-summary.log 2>&1
```

## Bot Commands

Once the bot is running, users can interact with it:

### Registration & Setup
- `/start <password>` - Register with invite password
- `/setup` - Launch configuration wizard (can be re-run anytime)
- `/profile` - View/edit profile description
- `/topics` - Edit relevant and excluded topics
- `/bulletins` - Toggle DOG/BOE/EU Funding bulletins

### Control
- `/pause` - Pause/resume daily notifications
- `/summary` - Get instant summary now
- `/help` - Show all available commands

### User Workflow

1. **Invitation**: Admin shares bot link + invite password
2. **Registration**: User runs `/start <password>`
3. **Setup Wizard**: 5-step process:
   - Profile description
   - Topics of interest
   - Topics to exclude
   - Bulletin selection (DOG/BOE/EU)
   - Confirmation
4. **Daily Summaries**: Automated at configured time (cron)
5. **On-demand**: Use `/summary` anytime for instant analysis

## Project Structure

```
boe-dog-summary/
├── src/
│   └── tg_summary/
│       ├── __init__.py          # Package initialization
│       ├── main.py              # Entry point with mode selection
│       ├── bot.py               # Cron mode: daily summary logic
│       ├── interactive_bot.py     # Bot mode: handlers & wizard
│       ├── config.py            # Configuration and constants
│       ├── llm.py               # OpenRouter API integration
│       ├── feed.py              # RSS feed fetching
│       ├── recipients.py        # User data management
│       └── markdown_fix.py      # Markdown/HTML utilities
├── recipients.json              # User database with invite password
├── .env.example                 # Environment variables template
├── .gitignore                  # Git ignore patterns
├── pyproject.toml              # Project configuration
└── README.md                   # This file
```

## Data Storage

User profiles are stored in `recipients.json`:

```json
{
  "invite_password": "SECRET123",
  "recipients": [
    {
      "name": "John Doe",
      "chat_id": "123456789",
      "bulletins": ["dog", "boe"],
      "profile": "Autónomo en Galicia con empresa tech",
      "relevance": {
        "yes": ["subvenciones pymes", "IA", "innovación"],
        "no": ["agricultura", "pesca"]
      },
      "is_active": true,
      "setup_complete": true
    }
  ]
}
```

- `invite_password`: Shared secret for new registrations
- `is_active`: Whether user receives daily summaries
- `setup_complete`: Whether user has finished initial setup

## Customization

### Changing Bulletins

Edit `config.py` to modify RSS URLs:

```python
DOG_RSS_URL = "https://www.xunta.gal/diario-oficial-galicia/rss/Sumario_es.rss"
BOE_RSS_URL = "https://www.boe.es/rss/boe.php"
EU_FUNDING_RSS_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/rss"
```

### Modifying LLM Prompts

Edit `recipients.py` to customize the analysis instructions:

- `_get_format_instructions()`: Output format rules
- `build_system_prompt()`: Analysis criteria

## Dependencies

- `feedparser` - RSS feed parsing
- `httpx` - Async HTTP client
- `python-telegram-bot` - Telegram API with conversation handlers
- `python-dotenv` - Environment variable management

## License

MIT License
