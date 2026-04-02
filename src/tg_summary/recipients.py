import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Bulletin = Literal["dog", "boe"]


@dataclass
class Recipient:
    name: str
    chat_id: str
    bulletins: list[Bulletin]
    profile: str
    relevance: dict[str, list[str]]


def _get_format_instructions() -> str:
    return """\
Por cada entrada relevante indica:
- Título breve (en negrita)
- Por qué es relevante (1 línea)
- Enlace como [Ver enlace](URL)
- Plazo si lo hay

Si no hay nada relevante, dilo en una línea.

FORMATO: Usa markdown simple. Negrita: **texto**. Enlaces: [texto](url). No uses caracteres especiales que requieran escape."""


def _build_relevance_text(relevance: dict[str, list[str]]) -> str:
    yes_items = "\n- ".join(relevance.get("yes", []))
    no_items = "\n- ".join(relevance.get("no", []))

    return f"""\
SÍ relevante:
- {yes_items}

NO relevante (ignorar siempre):
- {no_items}
"""


def build_system_prompt(
    bulletin_name: str, profile: str, relevance: dict[str, list[str]]
) -> str:
    bulletin_full_name = (
        "DOG (Diario Oficial de Galicia)"
        if bulletin_name == "dog"
        else "BOE (Boletín Oficial del Estado)"
    )

    return f"""\
Analiza el sumario del {bulletin_full_name} y extrae SOLO lo relevante para:
- {profile}

{_build_relevance_text(relevance)}

{_get_format_instructions()}
"""


def _resolve_env_vars(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"Environment variable {env_var} not set")
        return resolved
    return value


def load_recipients(config_path: Path | str = None) -> list[Recipient]:
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "recipients.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Recipients config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recipients = []
    for r in data.get("recipients", []):
        chat_id = _resolve_env_vars(str(r["chat_id"]))

        recipient = Recipient(
            name=r["name"],
            chat_id=chat_id,
            bulletins=r["bulletins"],
            profile=r["profile"],
            relevance=r["relevance"],
        )
        recipients.append(recipient)
        logger.info(
            "Loaded recipient: %s (chat_id: %s, bulletins: %s)",
            recipient.name,
            recipient.chat_id,
            recipient.bulletins,
        )

    logger.info("Total recipients loaded: %d", len(recipients))
    return recipients
