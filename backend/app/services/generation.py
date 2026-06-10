import json
import logging
import re
import traceback
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.flashcard import Flashcard, FlashcardOption
from app.models.study_plan import StudyPlan
from app.models.study_topic import StudyTopic
from app.models.topic_source import TopicSource
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.email import send_email

logger = logging.getLogger(__name__)

_STUDY_PLAN_SYSTEM = (
    "You are an expert educator and curriculum designer. Given a study topic,\n"
    "description, and source material, create a comprehensive, pedagogically\n"
    "sound study plan. Your plan must:\n"
    "1. Identify core concepts and their dependencies\n"
    "2. Group into 2–6 logical learning units\n"
    "3. For each unit: title, key learning objectives, specific sub-topics\n"
    "4. Conclude with expected competencies\n"
    "Output structured Markdown. Name exact concepts, formulas, definitions,\n"
    "relationships. No generic advice."
)

_FLASHCARD_SYSTEM = (
    "You are generating flashcards. Output ONLY valid JSON, no prose.\n"
    "Each card: {type, question, correct_answer, explanation, difficulty (1-5),\n"
    "options (array of 4 for multiple_choice, exactly 1 correct)}.\n"
    "Difficulty: 1=trivial definition, 3=requires understanding, 5=synthesis.\n"
    "Distribution: ~20% difficulty 1-2, ~50% difficulty 3, ~30% difficulty 4-5.\n"
    "Types: multiple_choice, exact_answer, yes_no, exam_question."
)


async def _call_ollama(url: str, model: str, system: str, user_msg: str) -> str:
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def _parse_units(plan_text: str) -> list[tuple[str, str]]:
    """Return list of (unit_title, unit_content) from Markdown study plan."""
    # Try ## headings first (expected from prompt)
    sections = re.split(r"\n(?=##\s)", plan_text)
    units = []
    for section in sections:
        lines = section.strip().split("\n")
        m = re.match(r"^##\s+(.*)", lines[0])
        if m:
            units.append((m.group(1).strip(), "\n".join(lines[1:]).strip()))

    # Fallback: any heading level
    if not units:
        sections = re.split(r"\n(?=#{1,3}\s)", plan_text)
        for section in sections:
            lines = section.strip().split("\n")
            m = re.match(r"^#{1,3}\s+(.*)", lines[0])
            if m:
                units.append((m.group(1).strip(), "\n".join(lines[1:]).strip()))

    # Final fallback: treat whole plan as one unit
    if not units:
        units = [("Study Material", plan_text)]

    return units


def _parse_flashcard_json(text: str) -> list[dict]:
    """Parse a JSON array of flashcard objects from LLM output."""
    cleaned = text.strip()
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("cards", "flashcards", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
    except json.JSONDecodeError:
        pass

    # Try to extract embedded array
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        return json.loads(match.group())

    raise ValueError(f"Could not parse flashcard JSON: {text[:500]!r}")


async def _generate_flashcards_for_unit(
    ollama_url: str, ollama_model: str, unit_title: str, unit_content: str
) -> list[dict]:
    user_msg = (
        f"Generate flashcards for the following study unit.\n\n"
        f"Unit: {unit_title}\n\n"
        f"{unit_content}\n\n"
        f"Generate at least 4 cards. Include at least one card of each type: "
        f"multiple_choice, exact_answer, yes_no, exam_question. "
        f"Output a JSON array of card objects only."
    )
    raw = await _call_ollama(ollama_url, ollama_model, _FLASHCARD_SYSTEM, user_msg)
    try:
        return _parse_flashcard_json(raw)
    except (ValueError, json.JSONDecodeError):
        # Retry once on parse failure
        raw2 = await _call_ollama(ollama_url, ollama_model, _FLASHCARD_SYSTEM, user_msg)
        return _parse_flashcard_json(raw2)


async def _persist_results(
    db: AsyncSession,
    topic: StudyTopic,
    plan_text: str,
    all_cards: list[dict],
) -> None:
    plan = StudyPlan(topic_id=topic.id, plan_text=plan_text)
    db.add(plan)
    await db.flush()

    for card_data in all_cards:
        card = Flashcard(
            plan_id=plan.id,
            card_type=card_data.get("type", "exact_answer"),
            question=card_data.get("question", ""),
            correct_answer=card_data.get("correct_answer", ""),
            explanation=card_data.get("explanation"),
            difficulty=int(card_data.get("difficulty", 3)),
        )
        db.add(card)
        await db.flush()

        if card_data.get("type") == "multiple_choice":
            options = card_data.get("options") or []
            correct = card_data.get("correct_answer", "")
            for opt_text in options:
                db.add(
                    FlashcardOption(
                        flashcard_id=card.id,
                        option_text=str(opt_text),
                        is_correct=(str(opt_text) == correct),
                    )
                )

    topic.status = "ready"
    topic.generation_error = None
    await db.commit()


async def run_generation(topic_id: str, user_id: str) -> None:
    error_tb: Optional[str] = None
    try:
        async with async_session_factory() as db:
            result = await db.execute(select(StudyTopic).where(StudyTopic.id == topic_id))
            topic = result.scalar_one()

            result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
            user_settings = result.scalar_one_or_none()
            if not user_settings or not user_settings.ollama_url or not user_settings.ollama_model:
                raise ValueError("Ollama URL and model must be configured in user settings")

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()

            result = await db.execute(
                select(TopicSource).where(TopicSource.topic_id == topic_id)
            )
            sources = result.scalars().all()

            combined_sources = "\n\n---\n\n".join(
                src.content for src in sources if src.content
            )[:80000]

            # Step 1 — study plan
            user_msg = f"Topic: {topic.title}\n"
            if topic.description:
                user_msg += f"Description: {topic.description}\n"
            if combined_sources:
                user_msg += f"\nSource Material:\n{combined_sources}"

            plan_text = await _call_ollama(
                user_settings.ollama_url,
                user_settings.ollama_model,
                _STUDY_PLAN_SYSTEM,
                user_msg,
            )

            # Step 2 — flashcard generation per unit
            units = _parse_units(plan_text)
            all_cards: list[dict] = []
            for unit_title, unit_content in units:
                cards = await _generate_flashcards_for_unit(
                    user_settings.ollama_url,
                    user_settings.ollama_model,
                    unit_title,
                    unit_content,
                )
                all_cards.extend(cards)

            # Step 3 — persist
            await _persist_results(db, topic, plan_text, all_cards)

            # Step 4 — email notification
            if user_settings.smtp_host:
                card_count = len(all_cards)
                try:
                    await send_email(
                        smtp_host=user_settings.smtp_host,
                        smtp_port=user_settings.smtp_port,
                        smtp_user=user_settings.smtp_user,
                        smtp_password=user_settings.smtp_password,
                        smtp_from=user_settings.smtp_from,
                        smtp_tls=user_settings.smtp_tls,
                        to=user.email,
                        subject=f"Your study topic '{topic.title}' is ready!",
                        html_body=(
                            f"<h2>Your study materials are ready!</h2>"
                            f"<p>Your study topic <strong>{topic.title}</strong> has been processed.</p>"
                            f"<p>We've created <strong>{card_count} flashcard{'s' if card_count != 1 else ''}</strong> "
                            f"to help you learn efficiently.</p>"
                            f"<p>Open the slopstudy app to start studying!</p>"
                        ),
                        text_body=(
                            f"Your study topic '{topic.title}' is ready!\n\n"
                            f"We've created {card_count} flashcard{'s' if card_count != 1 else ''} "
                            f"for your topic.\n\nOpen the slopstudy app to start studying!"
                        ),
                    )
                except Exception:
                    logger.warning(
                        "SMTP notification failed for topic %s", topic_id, exc_info=True
                    )

    except Exception:
        error_tb = traceback.format_exc()
        logger.error("Generation failed for topic %s", topic_id, exc_info=True)

    if error_tb:
        async with async_session_factory() as db:
            try:
                result = await db.execute(
                    select(StudyTopic).where(StudyTopic.id == topic_id)
                )
                topic = result.scalar_one_or_none()
                if topic:
                    topic.status = "failed"
                    topic.generation_error = error_tb
                    await db.commit()
            except Exception:
                logger.error("Could not persist generation error for topic %s", topic_id, exc_info=True)
