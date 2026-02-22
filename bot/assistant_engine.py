import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

import httpx

from bot.assistant_config_store import get_custom_prompt
from core.config import settings

logger = logging.getLogger(__name__)

ESCALATION_KEYWORDS = {
    "менеджер",
    "оператор",
    "человек",
    "жалоба",
    "договор",
    "счет",
    "счёт",
    "оплата",
    "предоплата",
    "срочно",
    "manager",
    "operator",
    "contract",
    "invoice",
    "payment",
    "urgent",
}
DISCOUNT_PATTERN = re.compile(r"(\d{1,3})\s*%")


@dataclass(slots=True)
class AssistantResult:
    reply: str
    escalate: bool = False
    reason: str = ""


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


class SalesAssistant:
    def __init__(self) -> None:
        self._history: dict[str, Deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=max(settings.ASSISTANT_HISTORY_MESSAGES, 2))
        )

    def _base_system_prompt(self) -> str:
        return (
            "Ты ассистент продаж компании BITX. Отвечай на русском, коротко и по делу. "
            "Твоя задача: консультировать, выявлять задачу, доводить до заявки.\n"
            "Правила:\n"
            f"1) Максимальная скидка: {settings.SALES_MAX_DISCOUNT_PCT}%.\n"
            "2) Не обещай точные сроки и финальный бюджет без уточнений.\n"
            "3) Не придумывай кейсы и гарантии, которых не было озвучено.\n"
            "4) Если запрос про договор/оплату/юридические условия — предложи подключить менеджера.\n"
            "5) Задавай максимум один уточняющий вопрос за сообщение, без давления.\n"
            "6) Если данных мало, мягко предложи следующий шаг.\n"
            "7) Не предлагай анкеты, формы, команды и кнопки; веди диалог только обычной перепиской.\n"
            "8) Используй уместные смайлики для дружелюбного тона (обычно 1-2 на сообщение).\n"
            "Контакты: Telegram @bitx_kg, Instagram @bitx_kg, Email info@bitx.kg."
        )

    async def _build_system_prompt(self) -> str:
        base = self._base_system_prompt()
        custom = await get_custom_prompt()
        if not custom:
            return base
        return f"{base}\n\nДополнительный сценарий от администратора:\n{custom}"

    def _trim_history(self, chat_key: str) -> None:
        max_chars = max(settings.ASSISTANT_MAX_HISTORY_CHARS, 500)
        history = self._history[chat_key]
        total = sum(len(item.get("text", "")) for item in history)
        while history and total > max_chars:
            dropped = history.popleft()
            total -= len(dropped.get("text", ""))

    def _append_history(self, chat_key: str, role: str, text: str) -> None:
        self._history[chat_key].append({"role": role, "text": text})
        self._trim_history(chat_key)

    def _enforce_discount_rule(self, text: str) -> AssistantResult | None:
        lowered = text.lower()
        if "скид" not in lowered and "discount" not in lowered:
            return None

        percents = [int(match) for match in DISCOUNT_PATTERN.findall(text)]
        if not percents:
            return None

        requested = max(percents)
        if requested <= settings.SALES_MAX_DISCOUNT_PCT:
            return None

        reply = (
            f"Могу предложить скидку до {settings.SALES_MAX_DISCOUNT_PCT}% в рамках текущих условий. "
            "Если нужна более гибкая цена, подключу менеджера и соберем индивидуальный пакет."
        )
        return AssistantResult(reply=reply, escalate=True, reason="discount_limit")

    def _needs_escalation(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in ESCALATION_KEYWORDS)

    def _fallback_reply(self, user_text: str) -> AssistantResult:
        if self._needs_escalation(user_text):
            return AssistantResult(
                reply=(
                    "Понял задачу. Подключаю менеджера, чтобы согласовать детали и условия. "
                    "Также можно написать в Telegram: @bitx_kg."
                ),
                escalate=True,
                reason="manual_request",
            )

        return AssistantResult(
            reply=(
                "Могу помочь с консультацией и предварительной оценкой. "
                "Коротко опишите задачу, желаемые сроки и ориентир по бюджету."
            )
        )

    async def _ask_llm(self, chat_key: str, user_text: str) -> str | None:
        if not settings.OPENAI_API_KEY:
            return None

        system_prompt = await self._build_system_prompt()
        history = list(self._history[chat_key])
        input_messages: list[dict] = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            }
        ]

        for item in history:
            role = item["role"]
            content_type = "output_text" if role == "assistant" else "input_text"
            input_messages.append(
                {
                    "role": role,
                    "content": [{"type": content_type, "text": item["text"]}],
                }
            )

        input_messages.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            }
        )

        endpoint = f"{settings.OPENAI_BASE_URL.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.OPENAI_MODEL,
            "input": input_messages,
            "max_output_tokens": settings.ASSISTANT_MAX_TOKENS,
            "temperature": 0.35,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                answer = _extract_output_text(data)
                return answer or None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:1500]
            err_code = ""
            try:
                err_code = (exc.response.json().get("error") or {}).get("code") or ""
            except Exception:
                pass

            if status == 429 and err_code == "insufficient_quota":
                logger.warning(
                    "Sales assistant LLM disabled by quota limit: status=%s code=%s body=%s",
                    status,
                    err_code,
                    body,
                )
            else:
                logger.error(
                    "Sales assistant LLM request failed: status=%s code=%s body=%s",
                    status,
                    err_code,
                    body,
                )
            return None
        except httpx.HTTPError:
            logger.exception("Sales assistant LLM transport error")
            return None

    async def reply(self, chat_id: str | int, user_text: str) -> AssistantResult:
        clean_text = (user_text or "").strip()
        if not clean_text:
            return AssistantResult(reply="Опишите задачу текстом, и я помогу с оценкой.")

        chat_key = str(chat_id)

        forced = self._enforce_discount_rule(clean_text)
        if forced:
            self._append_history(chat_key, "user", clean_text)
            self._append_history(chat_key, "assistant", forced.reply)
            return forced

        llm_reply = await self._ask_llm(chat_key=chat_key, user_text=clean_text)
        if not llm_reply:
            fallback = self._fallback_reply(clean_text)
            self._append_history(chat_key, "user", clean_text)
            self._append_history(chat_key, "assistant", fallback.reply)
            return fallback

        escalate = self._needs_escalation(clean_text)
        reason = "keyword" if escalate else ""
        if escalate and "подключ" not in llm_reply.lower():
            llm_reply = (
                f"{llm_reply}\n\n"
                "Чтобы согласовать коммерческие условия, подключаю менеджера."
            )

        self._append_history(chat_key, "user", clean_text)
        self._append_history(chat_key, "assistant", llm_reply)
        return AssistantResult(reply=llm_reply, escalate=escalate, reason=reason)
