"""Ollama client and the prompt engineering for study-plan + card generation."""
import json
import math
import re

import httpx

GENERATION_TIMEOUT = 600  # local models can be slow; topic generation is async anyway

LANG_NAMES = {"en": "English", "de": "German"}

MODE_LABELS = {
    "multiple_choice": "multiple choice",
    "exact": "exact written answer",
    "yes_no": "yes/no",
    "exam": "exam-style",
}


class OllamaError(Exception):
    pass


def _headers(user: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if user.get("ollama_api_key"):
        headers["Authorization"] = f"Bearer {user['ollama_api_key']}"
    return headers


async def chat_json(user: dict, system: str, prompt: str) -> dict:
    """One non-streaming chat call with JSON output mode. Returns parsed JSON."""
    url = user["ollama_url"].rstrip("/") + "/api/chat"
    payload = {
        "model": user["ollama_model"],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.6, "num_ctx": 8192},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=_headers(user))
    except httpx.HTTPError as e:
        raise OllamaError(f"Cannot reach Ollama at {user['ollama_url']}: {e}") from e
    if resp.status_code == 404:
        raise OllamaError(
            f"Model '{user['ollama_model']}' not found on the Ollama server. "
            f"Pull it first: ollama pull {user['ollama_model']}"
        )
    if resp.status_code != 200:
        raise OllamaError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}")
    content = resp.json().get("message", {}).get("content", "")
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    content = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise OllamaError("The model did not return valid JSON. Try a larger/more capable model.")


async def test_connection(user: dict) -> dict:
    """Lightweight connectivity + model check for the settings page."""
    base = user["ollama_url"].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(base + "/api/tags", headers=_headers(user))
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise OllamaError(f"Cannot reach Ollama: {e}") from e
    models = [m.get("name", "") for m in resp.json().get("models", [])]
    wanted = user["ollama_model"]
    available = any(m == wanted or m.split(":")[0] == wanted for m in models)
    return {"ok": True, "models": models, "model_available": available}


# ---------------------------------------------------------------- prompts

PLANNER_SYSTEM = """You are an expert learning designer and university instructor. You design \
rigorous, pedagogically sound study plans for spaced-repetition flashcard learning.

Design principles you MUST follow:
- Sequence units from foundational to advanced, following Bloom's taxonomy: first remembering \
core terminology and facts, then understanding relationships, then applying concepts to problems, \
then analyzing/evaluating edge cases and common misconceptions.
- Each unit must have a clear, testable focus. No vague filler units.
- Identify the concepts learners typically get wrong in this subject and make sure they are \
covered explicitly.
- If source material is provided, ground the plan in it and prioritize its content; fill genuine \
gaps with your domain knowledge and prefer the sources where they conflict.
- The plan must be realistic for flashcard study: factual anchors, definitions, distinctions, \
cause-effect relations, worked-problem patterns — not essay topics.

Respond ONLY with JSON, no prose, exactly this shape:
{
  "title": "concise topic title (max 8 words)",
  "overview": "2-3 sentences describing the learning path and goals",
  "units": [
    {
      "title": "unit title",
      "objectives": ["learning objective", ...],
      "key_concepts": ["concept", ...],
      "pitfalls": ["common mistake or misconception to test", ...]
    }
  ]
}
Use 4 to 7 units. Write all text in {language}."""

PLANNER_USER = """Create a study plan for the following request.

STUDY REQUEST:
{prompt}

ANSWER MODE the learner chose: {mode_label}
TOTAL FLASHCARDS that will be generated: {card_count}

{sources_block}"""

CARDS_SYSTEM = """You are an expert exam author and flashcard writer. You write precise, \
unambiguous flashcards for one unit of a study plan. Quality rules:

- Every card tests exactly ONE fact, distinction, or application. No double-barreled questions.
- Questions must be answerable without seeing the answer options elsewhere; no "all of the above".
- Cover the unit's objectives, key concepts AND its listed pitfalls/misconceptions.
- Prefer questions that force retrieval (e.g. "What is X?", "Which mechanism causes Y?") over \
recognition trivia.
- The "explanation" briefly teaches WHY the answer is correct (1-2 sentences).
- Assign difficulty honestly: 1=basic recall, 2=core knowledge, 3=relations/understanding, \
4=application/transfer, 5=tricky edge case or frequent exam trap.
- Vary difficulty across the unit: roughly 20% easy (1-2), 50% medium (2-3), 30% hard (4-5).

{mode_rules}

Respond ONLY with JSON, no prose, exactly:
{{"cards": [{{"type": "{card_type}", "question": "...", "answer": "...", "choices": [...], "explanation": "...", "difficulty": 1}}]}}
For non-multiple-choice cards use "choices": [].
Write all card text in {language}."""

MODE_RULES = {
    "multiple_choice": """MODE: multiple choice. Each card has "type":"multiple_choice", exactly 4 \
entries in "choices", and "answer" must be the exact text of the single correct choice. \
Distractors must be plausible and target real misconceptions — never obviously wrong joke options.""",
    "exact": """MODE: exact written answer. Each card has "type":"exact". The "answer" must be a \
short canonical answer of 1-4 words (a term, name, number, or formula) so that exact text matching \
is fair. Phrase the question so only that short answer fits. "choices" is always [].""",
    "yes_no": """MODE: yes/no questions. Each card has "type":"yes_no" and "answer" is exactly \
"yes" or "no". Write assertive statements or questions with a clear truth value. Aim for a roughly \
50/50 mix of yes and no answers, and include statements that sound true but are false (and vice \
versa). "choices" is always [].""",
    "exam": """MODE: exam-style questions. Write questions in the style and register of real exams \
for this subject (state exams, university finals, certification tests). If you know typical or \
classic exam questions for this subject, adapt them. Use "type":"multiple_choice" with 4 "choices" \
for questions that exams pose as MC, and "type":"open" with "choices": [] for short-answer exam \
questions (the learner self-grades those against your model answer). Mix both. The "answer" for \
open questions is a model solution of 1-3 sentences.""",
}

CARDS_USER = """STUDY TOPIC: {topic_title}
OVERALL PLAN OVERVIEW: {overview}

Write exactly {n} flashcards for this unit (unit {unit_no} of {unit_total}):
UNIT TITLE: {unit_title}
OBJECTIVES: {objectives}
KEY CONCEPTS: {key_concepts}
PITFALLS TO TEST: {pitfalls}

{avoid_block}{sources_block}"""


async def generate_plan(user: dict, topic: dict, sources_text: str) -> dict:
    language = LANG_NAMES.get(topic["language"], "English")
    sources_block = (
        f"SOURCE MATERIAL (provided by the learner, prioritize it):\n{sources_text}"
        if sources_text
        else "No source material provided — rely on your domain knowledge."
    )
    system = PLANNER_SYSTEM.replace("{language}", language)
    prompt = PLANNER_USER.format(
        prompt=topic["prompt"],
        mode_label=MODE_LABELS.get(topic["mode"], topic["mode"]),
        card_count=topic["card_count"],
        sources_block=sources_block,
    )
    plan = await chat_json(user, system, prompt)
    units = plan.get("units")
    if not isinstance(units, list) or not units:
        raise OllamaError("The model returned a study plan without units.")
    plan["units"] = units[:7]
    plan.setdefault("title", topic["prompt"][:60])
    plan.setdefault("overview", "")
    return plan


async def generate_unit_cards(
    user: dict, topic: dict, plan: dict, unit_index: int, n_cards: int, sources_text: str,
    avoid_questions: list[str] | None = None,
) -> list[dict]:
    unit = plan["units"][unit_index]
    language = LANG_NAMES.get(topic["language"], "English")
    mode = topic["mode"]
    card_type = {"multiple_choice": "multiple_choice", "exact": "exact",
                 "yes_no": "yes_no", "exam": "multiple_choice"}[mode]
    system = CARDS_SYSTEM.format(
        mode_rules=MODE_RULES[mode], card_type=card_type, language=language
    )
    sources_block = (
        f"RELEVANT SOURCE MATERIAL:\n{sources_text[:8000]}" if sources_text else ""
    )
    avoid_block = ""
    if avoid_questions:
        listing = "\n".join(f"- {q[:140]}" for q in avoid_questions[:50])
        avoid_block = (
            "The learner has ALREADY been asked the following questions. Your new cards must "
            "test DIFFERENT facts or angles — do not repeat or trivially rephrase any of these:\n"
            f"{listing}\n\n"
        )
    prompt = CARDS_USER.format(
        topic_title=plan.get("title", ""),
        overview=plan.get("overview", ""),
        n=n_cards,
        unit_no=unit_index + 1,
        unit_total=len(plan["units"]),
        unit_title=unit.get("title", ""),
        objectives="; ".join(unit.get("objectives", [])),
        key_concepts="; ".join(unit.get("key_concepts", [])),
        pitfalls="; ".join(unit.get("pitfalls", [])),
        avoid_block=avoid_block,
        sources_block=sources_block,
    )
    data = await chat_json(user, system, prompt)
    return _validate_cards(data.get("cards", []), mode)


def _validate_cards(raw_cards: list, mode: str) -> list[dict]:
    valid = []
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        question = str(card.get("question", "")).strip()
        answer = str(card.get("answer", "")).strip()
        if not question or not answer:
            continue
        ctype = str(card.get("type", "")).strip()
        choices = card.get("choices") or []
        if mode == "multiple_choice":
            ctype = "multiple_choice"
        elif mode == "exact":
            ctype = "exact"
        elif mode == "yes_no":
            ctype = "yes_no"
        elif mode == "exam" and ctype not in ("multiple_choice", "open"):
            ctype = "open" if not choices else "multiple_choice"

        if ctype == "multiple_choice":
            choices = [str(c).strip() for c in choices if str(c).strip()]
            if len(choices) < 2:
                continue
            # The correct answer must literally be one of the choices.
            if answer not in choices:
                lowered = [c.lower() for c in choices]
                if answer.lower() in lowered:
                    answer = choices[lowered.index(answer.lower())]
                else:
                    choices = choices[:3] + [answer]
            choices = choices[:4] if answer in choices[:4] else choices[:3] + [answer]
        elif ctype == "yes_no":
            norm = answer.lower().strip(".! ")
            if norm in ("yes", "ja", "true", "wahr"):
                answer = "yes"
            elif norm in ("no", "nein", "false", "falsch"):
                answer = "no"
            else:
                continue
            choices = []
        else:
            choices = []

        try:
            difficulty = max(1, min(5, int(card.get("difficulty", 2))))
        except (TypeError, ValueError):
            difficulty = 2
        valid.append({
            "type": ctype,
            "question": question,
            "answer": answer,
            "choices": choices,
            "explanation": str(card.get("explanation", "")).strip(),
            "difficulty": difficulty,
        })
    return valid


def cards_per_unit(total: int, units: int) -> int:
    return max(3, math.ceil(total / max(1, units)))


# ------------------------------------------------ enrichment (deep explanations)

ENRICH_SYSTEM = """You are a patient subject-matter tutor. A learner just answered a flashcard \
and now wants to actually UNDERSTAND the concept, not just memorize the answer.

Write a deeper explanation (5-9 sentences): why the answer is correct, the underlying mechanism \
or principle, how it connects to neighboring concepts, and the misconception that makes people \
get this wrong. Be concrete; use a short example if it helps.

You are given web search results. Select the 2-3 sources that are most trustworthy and useful \
for studying this exact concept (prefer encyclopedias, universities, official docs, textbooks; \
avoid forums and SEO spam). Only include sources from the provided list — never invent URLs. \
If none of the results are good, return an empty sources list.

Respond ONLY with JSON:
{"explanation": "...", "sources": [{"title": "...", "url": "..."}]}
Write the explanation in {language}."""

ENRICH_USER = """TOPIC: {topic_title}
FLASHCARD QUESTION: {question}
CORRECT ANSWER: {answer}

WEB SEARCH RESULTS:
{results_block}"""


async def enrich_card(user: dict, topic: dict, card: dict, results: list[dict]) -> dict:
    language = LANG_NAMES.get(topic["language"], "English")
    results_block = "\n".join(
        f"[{i + 1}] {r['title']}\n    URL: {r['url']}\n    {r['snippet']}"
        for i, r in enumerate(results)
    ) or "(no search results available)"
    data = await chat_json(
        user,
        ENRICH_SYSTEM.replace("{language}", language),
        ENRICH_USER.format(topic_title=topic["title"], question=card["question"],
                           answer=card["answer"], results_block=results_block),
    )
    explanation = str(data.get("explanation", "")).strip()
    allowed = {r["url"] for r in results}
    sources = [
        {"title": str(s.get("title", ""))[:150], "url": str(s.get("url", ""))[:500]}
        for s in (data.get("sources") or [])
        if isinstance(s, dict) and str(s.get("url", "")) in allowed
    ][:3]
    return {"explanation": explanation, "sources": sources}


# ------------------------------------------------ learning material per unit

MATERIAL_SYSTEM = """You are an expert textbook author. Write a compact, self-contained study \
text for ONE unit of a study plan — the material a learner reads AFTER first testing themselves \
on the flashcards (pre-testing effect: attempting retrieval before studying makes the subsequent \
reading stick better, so connect your text to the questions they will have struggled with).

Requirements:
- 250-400 words, plain text with short paragraphs (use \\n\\n between paragraphs).
- Cover the unit's objectives and key concepts in a logical arc; explicitly address the listed \
pitfalls ("a common mistake is ... because ...").
- Dense with substance, zero filler. Definitions precise, relations explicit.
- From the provided web search results, pick 2-4 genuinely good further-reading sources \
(encyclopedias, universities, official docs). Only use URLs from the list; never invent any.

Respond ONLY with JSON:
{"text": "...", "sources": [{"title": "...", "url": "..."}]}
Write in {language}."""

MATERIAL_USER = """TOPIC: {topic_title}
UNIT {unit_no}: {unit_title}
OBJECTIVES: {objectives}
KEY CONCEPTS: {key_concepts}
PITFALLS: {pitfalls}

SOURCE MATERIAL FROM THE LEARNER (use if relevant):
{sources_text}

WEB SEARCH RESULTS:
{results_block}"""


async def generate_unit_material(
    user: dict, topic: dict, plan: dict, unit_index: int,
    results: list[dict], sources_text: str,
) -> dict:
    unit = plan["units"][unit_index]
    language = LANG_NAMES.get(topic["language"], "English")
    results_block = "\n".join(
        f"[{i + 1}] {r['title']}\n    URL: {r['url']}\n    {r['snippet']}"
        for i, r in enumerate(results)
    ) or "(no search results available)"
    data = await chat_json(
        user,
        MATERIAL_SYSTEM.replace("{language}", language),
        MATERIAL_USER.format(
            topic_title=plan.get("title", ""), unit_no=unit_index + 1,
            unit_title=unit.get("title", ""),
            objectives="; ".join(unit.get("objectives", [])),
            key_concepts="; ".join(unit.get("key_concepts", [])),
            pitfalls="; ".join(unit.get("pitfalls", [])),
            sources_text=(sources_text or "(none)")[:4000],
            results_block=results_block,
        ),
    )
    allowed = {r["url"] for r in results}
    return {
        "unit_index": unit_index,
        "title": unit.get("title", ""),
        "text": str(data.get("text", "")).strip(),
        "sources": [
            {"title": str(s.get("title", ""))[:150], "url": str(s.get("url", ""))[:500]}
            for s in (data.get("sources") or [])
            if isinstance(s, dict) and str(s.get("url", "")) in allowed
        ][:4],
    }


# ------------------------------------------------ weakness report (nightly email)

REPORT_SYSTEM = """You are a supportive but rigorous study coach writing a personal review \
email. The learner got the flashcards below WRONG recently. Your job: turn their mistakes into \
understanding, using active-recall principles.

Structure (plain text, no markdown):
1. One warm, short opening line (no fluff beyond that).
2. For each weak area: state the question they missed, give the correct answer, then explain \
the concept properly in 3-5 sentences — mechanism, why their likely confusion happens, and a \
memorable anchor (mnemonic, contrast, or example).
3. End with 2-3 concrete retrieval-practice instructions (e.g. "Before your next session, try \
to recall X from memory, then check").

Keep the whole email under 600 words. Write in {language}.
Respond ONLY with JSON: {"body": "..."}"""

REPORT_USER = """LEARNER NAME: {name}

MISSED FLASHCARDS (grouped by topic):
{cards_block}"""


async def generate_weakness_report(user: dict, cards_block: str) -> str:
    language = LANG_NAMES.get(user.get("language", "en"), "English")
    data = await chat_json(
        user,
        REPORT_SYSTEM.replace("{language}", language),
        REPORT_USER.format(name=user["name"], cards_block=cards_block),
    )
    body = str(data.get("body", "")).strip()
    if not body:
        raise OllamaError("empty report body")
    return body
