import difflib
import json
import logging
import re
from typing import Optional

import httpx

from app.models.flashcard import Flashcard, FlashcardOption

logger = logging.getLogger(__name__)


def evaluate_multiple_choice(
    card: Flashcard,
    options: list[FlashcardOption],
    answer: str,
) -> bool:
    answer = answer.strip()
    # Direct text match with correct_answer
    if answer.lower() == card.correct_answer.strip().lower():
        return True
    # Match by index (0-based, 1-based, A-D, a-d) or option text
    for i, opt in enumerate(options):
        if answer in (str(i), str(i + 1), chr(ord("A") + i), chr(ord("a") + i)):
            return opt.is_correct
        if answer.lower() == opt.option_text.strip().lower():
            return opt.is_correct
    return False


def evaluate_yes_no(card: Flashcard, answer: str) -> bool:
    truthy = {"yes", "ja", "true", "1", "y", "oui", "si", "correct", "right"}
    falsy = {"no", "nein", "false", "0", "n", "non", "wrong", "incorrect"}

    answer_norm = answer.strip().lower()
    if answer_norm in truthy:
        answer_bool = True
    elif answer_norm in falsy:
        answer_bool = False
    else:
        return False

    correct_norm = card.correct_answer.strip().lower()
    if correct_norm in truthy:
        correct_bool = True
    elif correct_norm in falsy:
        correct_bool = False
    else:
        correct_bool = True

    return answer_bool == correct_bool


async def _call_ollama_eval(ollama_url: str, ollama_model: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{ollama_url.rstrip('/')}/api/chat",
            json={
                "model": ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def _parse_eval_json(raw: str) -> dict:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.MULTILINE).strip()
    return json.loads(cleaned)


async def evaluate_exact_answer(
    card: Flashcard,
    answer: str,
    ollama_url: Optional[str],
    ollama_model: Optional[str],
) -> bool:
    if ollama_url and ollama_model:
        prompt = (
            f'Is "{answer}" correct for "{card.question}"? '
            f'Canonical: "{card.correct_answer}". '
            f'Respond JSON {{"correct": bool, "reason": str}}'
        )
        try:
            raw = await _call_ollama_eval(ollama_url, ollama_model, prompt)
            data = _parse_eval_json(raw)
            return bool(data.get("correct", False))
        except Exception:
            logger.warning("Ollama exact-answer evaluation failed, using difflib", exc_info=True)

    ratio = difflib.SequenceMatcher(None, answer.lower(), card.correct_answer.lower()).ratio()
    return ratio >= 0.75


async def evaluate_exam_question(
    card: Flashcard,
    answer: str,
    ollama_url: Optional[str],
    ollama_model: Optional[str],
) -> tuple[bool, str]:
    if ollama_url and ollama_model:
        prompt = (
            f"Grade this answer to the following exam question.\n\n"
            f"Question: {card.question}\n"
            f"Expected answer: {card.correct_answer}\n"
            f"Student answer: {answer}\n\n"
            f"Score 0-100 based on completeness and correctness (pass threshold: 60). "
            f'Respond JSON {{"score": int, "feedback": str}}'
        )
        try:
            raw = await _call_ollama_eval(ollama_url, ollama_model, prompt)
            data = _parse_eval_json(raw)
            score = int(data.get("score", 0))
            feedback = str(data.get("feedback", ""))
            return score >= 60, feedback
        except Exception:
            logger.warning("Ollama exam evaluation failed, using difflib", exc_info=True)

    ratio = difflib.SequenceMatcher(None, answer.lower(), card.correct_answer.lower()).ratio()
    return ratio >= 0.6, "Evaluated offline due to LLM unavailability."
