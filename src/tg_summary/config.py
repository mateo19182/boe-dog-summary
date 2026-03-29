import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-preview")

DOG_RSS_URL = "https://www.xunta.gal/diario-oficial-galicia/rss/Sumario_es.rss"
BOE_RSS_URL = "https://www.boe.es/rss/boe.php"

_PROFILE = """\
Autónomo en Galicia con empresa tech (software fitness/deporte + proyectos IA).\
"""

_RELEVANCE = """\
SÍ relevante:
- Subvenciones y ayudas para autónomos, pymes, empresas tech
- Ayudas a I+D, innovación, digitalización, inteligencia artificial
- Subvenciones sector deporte, fitness, actividad física
- Normativa fiscal o laboral que afecte a autónomos o pymes
- Contratación pública en tech, software, deporte, IA

NO relevante (ignorar siempre):
- Igualdad, impacto social, género, violencia de género
- Gastronomía, turismo rural, agricultura, pesca, ganadería
- Medio ambiente, patrimonio cultural, urbanismo
- Oposiciones, nombramientos, ceses de personal
- Educación primaria/secundaria, becas escolares
- Sanidad pública, farmacia, colegios profesionales\
"""

_FORMAT = """\
Por cada entrada relevante indica:
- Título breve
- Por qué es relevante (1 línea)
- Enlace
- Plazo si lo hay

Si no hay nada relevante, dilo en una línea.

FORMATO: usa HTML de Telegram. Negrita con <b>, enlaces con <a href="url">texto</a>. No uses Markdown.\
"""

DOG_SYSTEM_PROMPT = f"""\
Analiza el sumario del DOG (Diario Oficial de Galicia) y extrae SOLO lo relevante para:
- {_PROFILE}

{_RELEVANCE}

{_FORMAT}\
"""

BOE_SYSTEM_PROMPT = f"""\
Analiza el sumario del BOE (Boletín Oficial del Estado) y extrae SOLO lo relevante para:
- {_PROFILE}

{_RELEVANCE}

{_FORMAT}\
"""
