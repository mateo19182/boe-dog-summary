import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-preview")

DOG_RSS_URL = "https://www.xunta.gal/diario-oficial-galicia/rss/Sumario_es.rss"
BOE_RSS_URL = "https://www.boe.es/rss/boe.php"
