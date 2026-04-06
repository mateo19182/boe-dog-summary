import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Bulletin = Literal["dog", "boe", "eu-funding"]


@dataclass
class Recipient:
    name: str
    chat_id: str
    bulletins: list[Bulletin]
    profile: str
    relevance: dict[str, list[str]]
    is_active: bool = True
    setup_complete: bool = False


def _get_format_instructions() -> str:
    return """\
INCLUIR SOLO items que requieren acción: convocatorias abiertas, plazos activos, oportunidades disponibles, cambios normativos que apliquen ahora.

EXCLUIR SIEMPRE:
- Nombramientos, ceses, reasignaciones de personal
- Proyectos aprobados/resueltos (ya concedidos, sin plazo de solicitud)
- Publicaciones meramente informativas sin acción requerida
- Acuerdos internos de órganos colegiados sin impacto externo
- Designaciones de representantes, vocales, comités
- Modificaciones presupuestarias sin convocatoria pública

Por cada entrada relevante indica:
- Título breve (en negrita)
- Por qué es relevante (1 línea)
- Enlace como [Ver enlace](URL)
- Plazo si lo hay (obligatorio para convocatorias)

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
    if bulletin_name == "dog":
        bulletin_full_name = "DOG (Diario Oficial de Galicia)"
    elif bulletin_name == "boe":
        bulletin_full_name = "BOE (Boletín Oficial del Estado)"
    elif bulletin_name == "eu-funding":
        bulletin_full_name = "Portal de Financiación y Contratos Públicos de la UE"
    else:
        bulletin_full_name = bulletin_name.upper()

    return f"""\
Analiza el sumario del {bulletin_full_name} y extrae SOLO items que requieran acción y sean relevantes para:
- {profile}

{_build_relevance_text(relevance)}

{_get_format_instructions()}

IMPORTANTE: Ve directo al grano. NO incluyas introducciones, saludos, ni frases como "Esta es la selección de..." o "He analizado el boletín...". Empieza directamente con el primer item relevante o, si no hay nada, con la línea indicando que no hay novedades."""


def _resolve_env_vars(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"Environment variable {env_var} not set")
        return resolved
    return value


def _get_config_path(config_path: Path | str = None) -> Path:
    if config_path is None:
        return Path(__file__).parent.parent.parent / "recipients.json"
    return Path(config_path)


def load_recipients(config_path: Path | str = None) -> list[Recipient]:
    config_path = _get_config_path(config_path)

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
            is_active=r.get("is_active", True),
            setup_complete=r.get("setup_complete", False),
        )
        recipients.append(recipient)
        logger.info(
            "Loaded recipient: %s (chat_id: %s, bulletins: %s, active: %s)",
            recipient.name,
            recipient.chat_id,
            recipient.bulletins,
            recipient.is_active,
        )

    logger.info("Total recipients loaded: %d", len(recipients))
    return recipients


def find_recipient_by_chat_id(
    chat_id: str, config_path: Path | str = None
) -> Recipient | None:
    """Find a recipient by their chat_id."""
    recipients = load_recipients(config_path)
    for recipient in recipients:
        if recipient.chat_id == str(chat_id):
            return recipient
    return None


def save_recipients(
    recipients: list[Recipient],
    invite_password: str | None = None,
    config_path: Path | str = None,
) -> None:
    """Save recipients list back to recipients.json."""
    config_path = _get_config_path(config_path)

    # Load existing to preserve invite_password if not provided
    existing_password = invite_password
    if existing_password is None and config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_password = data.get("invite_password", "")
        except (json.JSONDecodeError, FileNotFoundError):
            existing_password = ""

    # Convert recipients to dict, preserving env var placeholders for chat_id
    recipients_data = []
    for r in recipients:
        r_dict = asdict(r)
        # Try to restore env var placeholder if it matches
        r_dict["chat_id"] = r.chat_id
        recipients_data.append(r_dict)

    data = {"invite_password": existing_password or "", "recipients": recipients_data}

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Saved %d recipients to %s", len(recipients), config_path)


def update_recipient(
    chat_id: str, updates: dict, config_path: Path | str = None
) -> Recipient | None:
    """Update a specific recipient's fields and save."""
    recipients = load_recipients(config_path)

    for i, recipient in enumerate(recipients):
        if recipient.chat_id == str(chat_id):
            # Apply updates
            for key, value in updates.items():
                if hasattr(recipient, key):
                    setattr(recipient, key, value)

            save_recipients(recipients, config_path=config_path)
            logger.info("Updated recipient %s with %s", chat_id, updates.keys())
            return recipients[i]

    logger.warning("Recipient %s not found for update", chat_id)
    return None


def add_recipient(recipient: Recipient, config_path: Path | str = None) -> None:
    """Add a new recipient to the list."""
    recipients = load_recipients(config_path)

    # Check if already exists
    for r in recipients:
        if r.chat_id == recipient.chat_id:
            logger.warning("Recipient %s already exists, skipping", recipient.chat_id)
            return

    recipients.append(recipient)
    save_recipients(recipients, config_path=config_path)
    logger.info("Added new recipient: %s", recipient.name)


def remove_recipient(chat_id: str, config_path: Path | str = None) -> bool:
    """Remove a recipient by chat_id. Returns True if removed."""
    recipients = load_recipients(config_path)

    original_len = len(recipients)
    recipients = [r for r in recipients if r.chat_id != str(chat_id)]

    if len(recipients) < original_len:
        save_recipients(recipients, config_path=config_path)
        logger.info("Removed recipient: %s", chat_id)
        return True

    logger.warning("Recipient %s not found for removal", chat_id)
    return False
