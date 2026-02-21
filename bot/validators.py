import re

_link_re = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)


def _normalize(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def validate_name(s: str) -> tuple[bool, str]:
    s = _normalize(s)
    if len(s) < 2:
        return False, "Имя слишком короткое. Напишите минимум 2 символа."
    if _link_re.search(s):
        return False, "Ссылки в имени не нужны. Напишите просто имя."
    if len(s.split()) > 5:
        return False, "Слишком длинно для имени. Напишите короче."
    return True, s


def validate_company(s: str) -> tuple[bool, str]:
    s = _normalize(s)
    if len(s) < 2:
        return False, "Укажите компанию или нишу (минимум 2 символа)."
    if _link_re.search(s):
        return False, "Ссылку лучше оставить в описании задачи, а не в названии компании."
    return True, s


def validate_budget(s: str) -> tuple[bool, str]:
    s = _normalize(s).lower()
    if s in {"обсудим", "не знаю", "пока не знаю", "не определился", "не определилась"}:
        return True, "обсудим"

    cleaned = re.sub(r"[^\d]", "", s)
    if cleaned.isdigit() and len(cleaned) <= 9:
        return True, cleaned

    return False, "Бюджет: число (например 500 или 2000) либо «обсудим»."


def validate_details(s: str) -> tuple[bool, str]:
    s = _normalize(s)
    if len(s) < 10:
        return False, "Слишком мало деталей. Напишите хотя бы 1-2 предложения (от 10 символов)."
    if len(s) > 1200:
        return False, "Слишком длинно. Сожмите описание до 1-2 абзацев."
    if len(set(s.lower())) <= 3:
        return False, "Похоже на набор символов. Опишите задачу словами."
    return True, s
