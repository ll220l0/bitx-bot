import logging
import re
from dataclasses import dataclass, field
from html import escape

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import select

from core.config import settings
from db.models import Lead, LeadProfile
from db.session import async_session

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{7,}\d")
USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{3,32}")
BUDGET_RE = re.compile(
    r"(?:бюджет|budget|до|около|примерно|на сумму)\s*[:\-]?\s*([^\n]{2,50})",
    flags=re.IGNORECASE,
)
NAME_RE = re.compile(
    r"(?:меня зовут|мое имя|моё имя|я)\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\s]{1,60})",
    flags=re.IGNORECASE,
)
COMPANY_RE = re.compile(
    r"(?:компания|из компании|компании|ниша|сфера)\s*[:\-]?\s*([^\n,.]{2,100})",
    flags=re.IGNORECASE,
)
SERVICE_HINT_RE = re.compile(
    r"(?:нужен|нужно|хочу|интересует|сделать|разработать)\s+([^\n]{3,100})",
    flags=re.IGNORECASE,
)
TIMELINE_RE = re.compile(
    r"(?:срок|дедлайн|когда|до\s+\d{1,2}\.\d{1,2}|\d+\s*(?:дн|дня|дней|недел|месяц|месяца|месяцев))",
    flags=re.IGNORECASE,
)

REQUIREMENT_TAGS: dict[str, tuple[str, ...]] = {
    "Интеграции со сторонними сервисами": ("интеграц", "api", "amo", "битрикс", "google", "1с"),
    "Автоматизация процессов": ("автоматизац", "оптимизац", "сократить руч", "workflow"),
    "Лидогенерация и продажи": ("лид", "продаж", "заяв", "воронк", "конверс"),
    "Поддержка клиентов": ("поддержк", "чат", "faq", "консультац"),
    "Запуск MVP": ("mvp", "прототип", "пилот"),
    "Мобильный канал": ("мобил", "ios", "android", "приложен"),
}

QUESTION_BY_FIELD: dict[str, str] = {
    "name": "Если удобно, подскажите ваше имя.",
    "company": "Если удобно, уточните компанию или нишу проекта.",
    "service": "Если удобно, напишите, какая услуга в приоритете (сайт, бот, CRM, автоматизация).",
    "timeline": "Если уже понимаете сроки, подскажите желаемую дату запуска.",
    "budget": "Если есть ориентир, подскажите примерный бюджет.",
    "contact": "Оставьте удобный контакт для связи (телефон, @username или email).",
    "details": "Если удобно, добавьте ключевые требования к результату.",
}
FOLLOW_UP_PRIORITY: tuple[str, ...] = ("name", "service", "contact", "company", "timeline", "budget", "details")


@dataclass(slots=True)
class LeadCaptureResult:
    sent: bool = False
    lead_id: int | None = None
    missing_fields: list[str] = field(default_factory=list)
    follow_up_question: str | None = None


def _clamp(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _extract_contact(text: str, username: str | None) -> str | None:
    email = EMAIL_RE.search(text)
    if email:
        return email.group(0)

    phone = PHONE_RE.search(text)
    if phone:
        return re.sub(r"\s+", " ", phone.group(0)).strip()

    mention = USERNAME_RE.search(text)
    if mention:
        return mention.group(0)

    if username:
        return f"@{username}"
    return None


def _extract_budget(text: str) -> str | None:
    match = BUDGET_RE.search(text)
    if match:
        return _clamp(match.group(1), 50)

    numbers = re.findall(r"\d[\d\s]{2,}", text)
    lowered = text.lower()
    if numbers and ("сом" in lowered or "usd" in lowered or "$" in lowered):
        return _clamp(numbers[0], 50)
    return None


def _extract_name(text: str, full_name: str | None) -> str | None:
    match = NAME_RE.search(text)
    if match:
        return _clamp(match.group(1), 100)
    return _clamp(full_name, 100)


def _extract_company(text: str) -> str | None:
    match = COMPANY_RE.search(text)
    if match:
        return _clamp(match.group(1), 150)
    return None


def _extract_service(text: str) -> str | None:
    match = SERVICE_HINT_RE.search(text)
    if match:
        return _clamp(match.group(1), 100)

    lowered = text.lower()
    keywords = {
        "сайт": "Разработка сайта",
        "бот": "Разработка бота",
        "crm": "CRM",
        "приложен": "Мобильное приложение",
        "автоматизац": "Автоматизация",
        "лендинг": "Лендинг",
    }
    for key, label in keywords.items():
        if key in lowered:
            return label
    return None


def _extract_timeline(text: str) -> str | None:
    if TIMELINE_RE.search(text):
        return _clamp(text, 120)
    return None


def _merge_details(old_value: str | None, text: str) -> str:
    chunk = text.strip()
    if not chunk:
        return (old_value or "").strip()

    previous = (old_value or "").strip()
    if chunk in previous:
        return previous

    merged = f"{previous}\n- {chunk}" if previous else f"- {chunk}"
    return merged[:4000]


def _detail_items(details: str | None) -> list[str]:
    if not details:
        return []

    items: list[str] = []
    for raw in details.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line and line not in items:
            items.append(line)
    return items


def _derive_tags(items: list[str]) -> list[str]:
    joined = " ".join(items).lower()
    tags: list[str] = []
    for label, keys in REQUIREMENT_TAGS.items():
        if any(key in joined for key in keys):
            tags.append(label)
    return tags[:5]


def _guess_timeline(items: list[str]) -> str | None:
    for item in items:
        candidate = _extract_timeline(item)
        if candidate:
            return candidate
    return None


def _detect_missing_fields(profile: LeadProfile) -> list[str]:
    items = _detail_items(profile.details)
    timeline = _guess_timeline(items)
    missing: list[str] = []

    if not profile.name:
        missing.append("name")
    if not profile.company:
        missing.append("company")
    if not profile.service:
        missing.append("service")
    if not timeline:
        missing.append("timeline")
    if not profile.budget:
        missing.append("budget")
    if not profile.contact:
        missing.append("contact")

    details_len = len((profile.details or "").strip())
    if details_len < max(settings.AUTO_LEAD_MIN_DETAILS_CHARS, 20):
        missing.append("details")

    return missing


def _build_follow_up_question(missing_fields: list[str]) -> str | None:
    if not missing_fields:
        return None
    for key in FOLLOW_UP_PRIORITY:
        if key in missing_fields:
            return QUESTION_BY_FIELD.get(key)
    return QUESTION_BY_FIELD.get(missing_fields[0])


def _should_ask_follow_up(profile: LeadProfile, missing_fields: list[str]) -> bool:
    if not missing_fields:
        return False

    # Ask gradually, not after every user message.
    if int(profile.message_count or 0) < 2:
        return False
    if int(profile.message_count or 0) % 2 != 0:
        return False

    # If only details are missing, ask later to avoid pressure.
    if missing_fields == ["details"] and int(profile.message_count or 0) < 6:
        return False

    return True


def _is_profile_ready(profile: LeadProfile) -> bool:
    if profile.sent_to_managers:
        return False
    if profile.message_count < max(settings.AUTO_LEAD_MIN_MESSAGES, 1):
        return False
    return not _detect_missing_fields(profile)


def _build_goal(service: str, tags: list[str]) -> str:
    if "Лидогенерация и продажи" in tags:
        return "Увеличить поток заявок и ускорить обработку клиентов."
    if "Автоматизация процессов" in tags:
        return "Снизить ручную нагрузку и ускорить операционные процессы."
    if "Поддержка клиентов" in tags:
        return "Повысить качество и скорость клиентской коммуникации."
    return f"Реализовать задачу клиента по направлению: {service.lower()}."


def _build_scope(service: str, tags: list[str]) -> str:
    base = f"{service}."
    if not tags:
        return base
    return f"{service}. Приоритетные блоки: {', '.join(tags)}."


def _build_internal_summary(
    *,
    name: str,
    company: str,
    service: str,
    budget: str,
    contact: str,
    timeline: str | None,
    tags: list[str],
) -> str:
    lines = [
        f"Клиент: {name}",
        f"Компания/ниша: {company}",
        f"Услуга: {service}",
        f"Бюджет: {budget}",
        f"Сроки: {timeline or 'не указаны'}",
        f"Контакт: {contact}",
    ]
    if tags:
        lines.append(f"Приоритеты: {', '.join(tags)}")
    return "\n".join(lines)[:1200]


def _format_card(lead: Lead, profile: LeadProfile) -> str:
    items = _detail_items(profile.details)
    tags = _derive_tags(items)
    timeline = _guess_timeline(items)

    goal = _build_goal(lead.service, tags)
    scope = _build_scope(lead.service, tags)
    context_items = tags or ["Требуется уточнение функционального объема"]
    context_text = "• " + "\n• ".join(escape(item) for item in context_items)

    card = (
        f"🧾 <b>Новая карточка клиента</b> (#{lead.id})\n\n"
        f"<b>Клиент</b>: {escape(lead.name)}\n"
        f"<b>Компания/ниша</b>: {escape(lead.company)}\n"
        f"<b>Контакт</b>: {escape(lead.contact)}\n"
        f"<b>Telegram</b>: {escape(profile.tg_username or 'no_username')}\n"
        f"<b>Chat ID</b>: <code>{profile.chat_id}</code>\n"
        f"<b>Источник</b>: {escape(lead.source)}\n\n"
        f"<b>Цель клиента</b>\n{escape(goal)}\n\n"
        f"<b>Контекст задачи</b>\n{escape(scope)}\n\n"
        f"<b>Бюджет</b>: {escape(lead.budget)}\n"
        f"<b>Сроки</b>: {escape(timeline or 'Требуют уточнения')}\n\n"
        f"<b>Важные акценты</b>\n{context_text}\n\n"
        "<b>Следующий шаг для менеджера</b>\n"
        "Связаться с клиентом, подтвердить объем, сроки и подготовить коммерческое предложение."
    )
    return card[:3900]


async def _notify_managers(card_text: str, bot: Bot | None) -> None:
    chat_ids = settings.notification_chat_ids()
    if not chat_ids:
        return

    created_bot: Bot | None = None
    client = bot
    if client is None:
        if not settings.BOT_TOKEN:
            return
        created_bot = Bot(
            settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        client = created_bot

    try:
        for chat_id in chat_ids:
            try:
                await client.send_message(chat_id, card_text)
            except Exception:
                logger.exception("Failed to send lead card to chat_id=%s", chat_id)
    finally:
        if created_bot is not None:
            await created_bot.session.close()


async def process_lead_capture(
    *,
    chat_id: int,
    user_id: int | None,
    username: str | None,
    full_name: str | None,
    user_text: str,
    bot: Bot | None = None,
) -> LeadCaptureResult:
    if not settings.AUTO_LEAD_CAPTURE_ENABLED:
        return LeadCaptureResult()

    text = (user_text or "").strip()
    if not text:
        return LeadCaptureResult()

    lead: Lead | None = None
    profile_snapshot: LeadProfile | None = None

    async with async_session() as session:
        result = await session.execute(select(LeadProfile).where(LeadProfile.chat_id == chat_id))
        profile = result.scalar_one_or_none()

        if profile is None:
            profile = LeadProfile(
                chat_id=chat_id,
                tg_user_id=user_id,
                tg_username=username,
                name=_extract_name(text, full_name),
                company=_extract_company(text),
                service=_extract_service(text),
                budget=_extract_budget(text),
                contact=_extract_contact(text, username),
                details=_merge_details(None, text),
                message_count=1,
            )
            session.add(profile)
        else:
            profile.tg_user_id = user_id or profile.tg_user_id
            profile.tg_username = username or profile.tg_username
            profile.message_count = int(profile.message_count or 0) + 1
            profile.details = _merge_details(profile.details, text)

            if not profile.name:
                profile.name = _extract_name(text, full_name)
            if not profile.company:
                profile.company = _extract_company(text)
            if not profile.service:
                profile.service = _extract_service(text)
            if not profile.budget:
                profile.budget = _extract_budget(text)
            if not profile.contact:
                profile.contact = _extract_contact(text, username)

        missing_fields = _detect_missing_fields(profile)
        follow_up_question = (
            _build_follow_up_question(missing_fields)
            if _should_ask_follow_up(profile, missing_fields)
            else None
        )

        if not _is_profile_ready(profile):
            await session.commit()
            return LeadCaptureResult(
                sent=False,
                missing_fields=missing_fields,
                follow_up_question=follow_up_question,
            )

        items = _detail_items(profile.details)
        tags = _derive_tags(items)
        timeline = _guess_timeline(items)

        lead = Lead(
            source="telegram_ai",
            name=_clamp(profile.name or full_name or "Клиент", 100) or "Клиент",
            company=_clamp(profile.company or "Частный клиент", 150) or "Частный клиент",
            service=_clamp(profile.service or "Консультация", 100) or "Консультация",
            budget=_clamp(profile.budget or "Обсуждается", 50) or "Обсуждается",
            contact=_clamp(profile.contact or f"chat_id:{chat_id}", 100) or f"chat_id:{chat_id}",
            details=_build_internal_summary(
                name=_clamp(profile.name or full_name or "Клиент", 100) or "Клиент",
                company=_clamp(profile.company or "Частный клиент", 150) or "Частный клиент",
                service=_clamp(profile.service or "Консультация", 100) or "Консультация",
                budget=_clamp(profile.budget or "Обсуждается", 50) or "Обсуждается",
                contact=_clamp(profile.contact or f"chat_id:{chat_id}", 100) or f"chat_id:{chat_id}",
                timeline=timeline,
                tags=tags,
            ),
        )
        session.add(lead)
        await session.flush()

        profile.sent_to_managers = True
        profile.sent_lead_id = lead.id
        profile_snapshot = profile

        await session.commit()
        await session.refresh(lead)

    if lead is None or profile_snapshot is None:
        return LeadCaptureResult()

    try:
        await _notify_managers(_format_card(lead, profile_snapshot), bot=bot)
    except Exception:
        logger.exception("Failed to notify managers for lead_id=%s", lead.id)

    return LeadCaptureResult(sent=True, lead_id=lead.id)
