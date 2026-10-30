import asyncio
import datetime
import json
import logging
import random
import re
import time
import unicodedata

from openai import APIError, AsyncOpenAI, AuthenticationError, RateLimitError

from . import config

logger = logging.getLogger(__name__)

MAX_JD_CHARS = 8000
MAX_RESUME_CHARS = 12000

CRITERIA = ["skills", "experience", "education", "fit"]
DEFAULT_WEIGHTS = {"skills": 40, "experience": 30, "education": 15, "fit": 15}
MAX_MUST_HAVES = 6
MAX_EDITED_MUST_HAVES = 10
PRESENT_WORDS = {"present", "current", "now", "till date", "to date", "ongoing"}
YEARS_PATTERN = re.compile(r"\d+(\.\d+)?\s*\+?\s*(years?|yrs?)\b", re.IGNORECASE)
DEGREE_WORDS = r"degree|bachelor[’']?s?|master[’']?s|diploma|ph\.?d|doctorate|mba|bba|bsc|msc|bcom|mcom|btech|mtech"
DEGREE_PATTERN = re.compile(rf"\b({DEGREE_WORDS})\b", re.IGNORECASE)
QUALIFICATION_PATTERN = re.compile(
    rf"\b({DEGREE_WORDS}|licen[cs]e[ds]?|certifi\w*|chartered|registered|registration|qualification|acca|cpa|cfa|cima)\b",
    re.IGNORECASE,
)
UNFINISHED_PATTERN = re.compile(r"not\s+(yet\s+)?(completed?|finished)|in\s+progress|expected|pursuing|ongoing", re.IGNORECASE)
OPTIONAL_PATTERN = re.compile(r"equivalent\s+(\w+\s+)?experience|\bpreferred\b|\bdesirable\b", re.IGNORECASE)
RATE_LIMIT_RETRIES = 4

SYSTEM_PROMPT = (
    "You are a senior HR recruiter with experience hiring across all departments. "
    "Be objective, evidence-based, and practical: credit genuine qualifications while understanding "
    "real-world nuances (e.g., treat equivalent terms, reasonable experience overlap like 3.8 vs 4 years, "
    "or close skill synonyms as matching). "
    "Your goal is to screen candidates fairly, avoiding both over-strict literal disqualifications "
    "and false claims. Judge job-relevant qualifications only; ignore name, gender, age, religion, "
    "nationality, marital status, photos, and personal attributes. "
    "Respond with a single valid JSON object and nothing else."
)

JD_PROMPT = """Analyse this job description so that every candidate can be screened against it in a consistent yet practical manner.

1. Decide how important each criterion is for THIS role. Weights are whole numbers that add up to 100:
  - skills: job-specific skills, tools, knowledge and competencies
  - experience: relevant work experience, years and seniority
  - education: degrees, certifications and licenses
  - fit: fit with the role's responsibilities, domain and industry
   Base the weights on what the JD emphasises. For example, an entry-level role weighs education more,
   a senior role weighs experience more, and a licensed role (doctor, CA, pilot) weighs education/certifications more.

2. Minimum experience: if the JD states a minimum number of years of experience, put the exact number in
   "min_experience_years" and describe it in "experience_requirement" (e.g. "4+ years of accounting experience").
   Otherwise use null for both. Do not include experience years in "must_haves" (experience will be evaluated separately).

3. List MUST-HAVE requirements. HR can mark a must-have as a deal-breaker that rejects every candidate missing it,
   so keep them few, broad and checkable on a CV. A must-have is something a candidate would list on a CV by name: a degree, license,
   certification, language, or a core tool, technology or skill area the job cannot be done without.
   - If the JD names a required degree or qualification (often under "Qualification" or "Education"), ALWAYS include
     it, listed first, with the alternatives the JD allows (e.g. "Bachelor's or Master's in Finance or related field").
   - When the JD lists many required tools or skills, group them into a few broad items, one per area, joined with
     "or", so a candidate needs a solid core rather than every item (e.g. "SAP or Oracle ERP", "Python or R for data
     analysis", "Java or C# backend development"). NEVER write one item that demands every tool in a list.
   - Name the skill only, without depth qualifiers such as "advanced", "expert", "design and optimization" or
     "secure" (write "Financial modelling", not "Advanced financial modelling and forecast optimization"). Depth is
     judged in the skills rating.
   - NEVER include practices, standards, methods or duties: things a person does on the job but rarely lists by name
     on a CV (e.g. following security or quality standards, best practices, testing, reviews, documentation,
     optimization, reporting routines). These are judged in the skills rating instead.
   - NEVER include soft skills or leadership (e.g. problem solving, communication, teamwork, team management);
     seniority and leadership are judged in the experience and fit ratings.
   - NEVER include preferred, "nice to have", "plus", or "good to have" skills; put them in "nice_to_haves".
   - When in doubt, leave it out.
   Maximum {max_must_haves}. An empty list is fine.

4. Deal-breakers: copy into "deal_breakers", word for word, only the must-haves that are formal qualifications the
   JD strictly requires: a degree, a professional license, or a legally required certification. NEVER include
   skills, tools, technologies, languages, practices or experience. Leave a qualification out when the JD accepts
   an alternative (e.g. "or equivalent experience") or calls it preferred. An empty list is fine.

Return JSON with exactly these keys:
{{
  "job_title": "string",
  "department": "string",
  "seniority": "string, e.g. Entry, Mid, Senior, Manager",
  "weights": {{"skills": int, "experience": int, "education": int, "fit": int}},
  "weight_reason": "one sentence explaining the weights",
  "min_experience_years": number or null,
  "experience_requirement": "string or null",
  "must_haves": ["string"],
  "deal_breakers": ["copied exactly from must_haves"],
  "nice_to_haves": ["string"]
}}

=== JOB DESCRIPTION ===
{jd}
"""

RESUME_PROMPT = """Today's date is {today}. Evaluate the candidate's resume against the job description with a balanced HR mindset.

First, list every job, internship, or work position in "positions". Copy the dates as YYYY-MM
(use month 01 when only the year is given) and write "Present" for a current job. Set "relevant" to true
when the work is relevant to the role in this JD. Leave out education. Do not calculate total years yourself:
the app calculates total years from these dates.

Rate the candidate from 0 to 10 on each criterion:
- skills: job-specific skills, tools, knowledge, and competencies asked in JD
- experience: relevant work experience, years, and seniority ("Present" means {today})
- education: degrees, certifications, and licenses asked in JD
- fit: fit with role responsibilities, domain, and industry
Rating guide: 9-10 fully meets or exceeds; 7-8 meets most; 5-6 partly meets; 2-4 meets little; 0-1 nothing relevant.
Judge experience and fit against the seniority the role needs: for a senior, lead or manager role, a fresh graduate,
intern or junior with no comparable responsibility rates 0-3, however many skills they list.
Soft skills get credit ONLY when backed by concrete achievements or responsibilities on the resume.

Evaluating Requirements & Rules:
1. EXPERIENCE TOLERANCE: Be realistic. If a candidate has ~3.7 - 3.9 years of relevant experience for a 4-year requirement, treat it as substantially meeting the expectation. Do NOT harshly penalize minor experience gaps if work quality and skills align.
2. MUST-HAVES EVALUATION:
   - "met" is `true` when the resume names the requirement or a direct, standard equivalent (e.g. MySQL for "SQL databases", ACCA for "professional accounting qualification"). For a requirement with alternatives ("A or B", "A, B or C"), one alternative is enough. Only check that the skill itself appears; how deep or advanced it is belongs in the ratings, not here.
   - "met" is `false` when the resume does not mention it, or contradicts it. A degree still in progress ("expected 2027") does not meet a degree requirement; a degree that ended before {today} is completed.
   - "met" is `null` when you can only infer it (the candidate "likely", "probably" or "implicitly" has it). Never mark `true` on inference.
   - "evidence": when met is true, copy the exact words from the resume that show it (a short quote, no paraphrasing). Otherwise write "Not mentioned in resume" or explain briefly.
   - For a degree requirement, when several of the candidate's degrees could meet it, judge and quote one that is already completed (e.g. a finished Bachelor's rather than a Master's still in progress).
   - "degree_end": for a degree requirement, copy the end or graduation date of the degree you quoted in "evidence" (or, when met is false, of the closest degree) as YYYY-MM or YYYY, or write "Present" or "Expected YYYY" exactly as the resume shows it. Use null for other requirements or when the resume gives no date.

Must-have requirements:
{must_haves}

Return JSON with exactly these keys:
{{
  "candidate_name": "string",
  "email": "string or null",
  "phone": "string or null",
  "current_title": "string or null",
  "positions": [{{"title": "string", "company": "string or null", "start": "YYYY-MM", "end": "YYYY-MM or Present", "relevant": true or false}}],
  "ratings": {{"skills": int, "experience": int, "education": int, "fit": int}},
  "must_haves": [{{"requirement": "copied exactly from the list above", "met": true, false or null, "evidence": "string", "degree_end": "string or null"}}],
  "matched_skills": ["JD requirements the resume clearly shows, by name or a direct equivalent"],
  "missing_skills": ["important JD requirements not found in the resume"],
  "strengths": ["up to 4 short points"],
  "concerns": ["up to 4 short points"],
  "summary": "2-3 sentences explaining the candidate's fit, noting any acceptable minor gaps or strong trade-offs for HR"
}}

=== JOB DESCRIPTION ===
{jd}

=== RESUME ===
{resume}
"""

MODEL_LIST_TTL = 60
MODEL_LIST_TIMEOUT = 5

_clients: dict[str, tuple[asyncio.AbstractEventLoop, AsyncOpenAI]] = {}
_model_lists: dict[str, tuple[float, list[str]]] = {}


def _get_client(provider: config.Provider) -> AsyncOpenAI:
    loop = asyncio.get_running_loop()
    cached = _clients.get(provider.id)
    if cached is None or cached[0] is not loop:
        client = AsyncOpenAI(
            api_key=provider.api_key or "not-needed",
            base_url=provider.base_url,
            timeout=provider.timeout,
            max_retries=0,
        )
        cached = _clients[provider.id] = (loop, client)
    return cached[1]


async def provider_models(provider: config.Provider) -> list[str]:
    if provider.models:
        return list(provider.models)
    cached = _model_lists.get(provider.id)
    if cached and time.monotonic() - cached[0] < MODEL_LIST_TTL:
        return cached[1]
    page = await _get_client(provider).models.list(timeout=MODEL_LIST_TIMEOUT)
    models = sorted(m.id for m in page.data)
    _model_lists[provider.id] = (time.monotonic(), models)
    return models


async def available_models() -> list[dict]:
    async def describe(provider: config.Provider) -> dict:
        try:
            return {"id": provider.id, "label": provider.label, "models": await provider_models(provider), "error": None}
        except Exception as exc:
            logger.warning("Could not list the models of %s (%s): %s", provider.label, provider.base_url, exc)
            return {"id": provider.id, "label": provider.label, "models": [], "error": "Not reachable"}

    return list(await asyncio.gather(*(describe(p) for p in config.PROVIDERS.values())))


async def resolve_model(provider_id: str, model: str) -> tuple[config.Provider, str]:
    provider_id = (provider_id or config.DEFAULT_PROVIDER).lower()
    provider = config.PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(f"Unknown AI provider '{provider_id}'.")
    models = await provider_models(provider)
    if not model:
        model = config.DEFAULT_MODEL if provider_id == config.DEFAULT_PROVIDER and config.DEFAULT_MODEL else ""
        model = model or (models[0] if models else "")
    if model not in models:
        raise ValueError(f"Model '{model}' is not available on {provider.label}.")
    return provider, model


def categorize(score: int) -> str:
    if score > 77:
        return "Highly Suitable"
    if score > 50:
        return "Suitable"
    if score > 40:
        return "Moderate"
    return "Not Suitable"


async def analyze_jd(jd_text: str, provider: config.Provider, model: str) -> dict:
    prompt = JD_PROMPT.format(jd=jd_text[:MAX_JD_CHARS], max_must_haves=MAX_MUST_HAVES)
    data, _ = await _complete_json(prompt, 4000, provider, model)
    min_years = _number(data.get("min_experience_years"))
    if not min_years or min_years <= 0:
        min_years = None
    must_haves = _str_list(data.get("must_haves"))
    if min_years:
        must_haves = [m for m in must_haves if not YEARS_PATTERN.search(m)]
    must_haves = must_haves[:MAX_MUST_HAVES]
    by_text = {m.lower(): m for m in must_haves}
    deal_breakers = [
        by_text[d.lower()]
        for d in _str_list(data.get("deal_breakers"))
        if d.lower() in by_text and QUALIFICATION_PATTERN.search(d) and not OPTIONAL_PATTERN.search(d)
    ]
    return clean_jd_analysis(
        {**data, "min_experience_years": min_years, "must_haves": must_haves, "deal_breakers": deal_breakers}
    )

def clean_jd_analysis(data) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Invalid job description analysis.")
    min_years = _number(data.get("min_experience_years"))
    if not min_years or min_years <= 0:
        min_years = None
    must_haves = list(dict.fromkeys(_str_list(data.get("must_haves"))))[:MAX_EDITED_MUST_HAVES]
    return {
        "job_title": _str(data.get("job_title")) or "Untitled role",
        "department": _str(data.get("department")),
        "seniority": _str(data.get("seniority")),
        "weights": _normalize_weights(data.get("weights")),
        "weight_reason": _str(data.get("weight_reason")) or "",
        "min_experience_years": min_years,
        "experience_requirement": (
            _str(data.get("experience_requirement")) or f"Minimum {min_years:g} years of relevant experience"
        ) if min_years else None,
        "must_haves": must_haves,
        "deal_breakers": [d for d in _str_list(data.get("deal_breakers")) if d in must_haves],
        "nice_to_haves": _str_list(data.get("nice_to_haves"))[:10],
    }

async def evaluate_resume(jd_text: str, jd: dict, resume_text: str, provider: config.Provider, model: str) -> dict:
    today = datetime.date.today()
    must_haves = "\n".join(f"- {m}" for m in jd["must_haves"]) or "(none - return an empty list)"
    resume = resume_text[:MAX_RESUME_CHARS]
    prompt = RESUME_PROMPT.format(
        today=today.strftime("%B %Y"),
        must_haves=must_haves,
        jd=jd_text[:MAX_JD_CHARS],
        resume=resume,
    )
    data, used_model = await _complete_json(prompt, 6000, provider, model)
    return {**_normalize_resume(data, jd, today, resume), "ai_model": f"{used_model} ({provider.label})"}

async def _complete_json(prompt: str, max_tokens: int, provider: config.Provider, model: str) -> tuple[dict, str]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    models = [model] + ([provider.fallback_model] if provider.fallback_model not in ("", model) else [])
    for i, current in enumerate(models):
        try:
            return await _complete_with(provider, current, messages, max_tokens), current
        except AuthenticationError:
            raise
        except (APIError, ValueError) as exc:
            if i == len(models) - 1:
                raise
            logger.warning("Model %s [%s] failed (%s), falling back to %s", current, provider.id, exc, models[i + 1])

async def _complete_with(provider: config.Provider, model: str, messages: list[dict], max_tokens: int) -> dict:
    last_error: Exception | None = None
    for attempt in (1, 2):
        response = await _create(provider, model, messages, max_tokens)
        content = response.choices[0].message.content or ""
        try:
            return _extract_json(content)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("Model %s [%s] returned unreadable JSON (attempt %d of 2): %s", model, provider.id, attempt, exc)
            logger.debug("Unreadable response from %s [%s]: %.3000s", model, provider.id, content)
    raise ValueError(f"Model returned an unreadable response: {last_error}")

async def _create(provider: config.Provider, model: str, messages: list[dict], max_tokens: int):
    extra = {"reasoning_effort": provider.reasoning_effort} if provider.reasoning_effort else {}
    if provider.json_mode:
        extra["response_format"] = {"type": "json_object"}
    name = f"{model} [{provider.id}]"
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        start = time.perf_counter()
        try:
            response = await _get_client(provider).chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                **extra,
            )
            _log_response(name, response, time.perf_counter() - start)
            # a prompt that fills the context window was cut off by the server
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            if provider.context_length and prompt_tokens >= provider.context_length * 0.9:
                logger.warning(
                    "Model %s got %d prompt tokens of a %d-token context, so the prompt was probably cut off; "
                    "raise %s_CONTEXT_LENGTH", name, prompt_tokens, provider.context_length, provider.id.upper(),
                )
            return response
        except APIError as exc:
            if not isinstance(exc, RateLimitError):
                logger.warning("Model %s failed after %.1fs: %s: %s", name, time.perf_counter() - start, type(exc).__name__, exc)
                raise
            if attempt == RATE_LIMIT_RETRIES:
                raise
            logger.warning("Rate limited by %s, retry %d of %d", name, attempt + 1, RATE_LIMIT_RETRIES)
            await asyncio.sleep(3 * 2**attempt + random.random())

def _log_response(model: str, response, seconds: float) -> None:
    usage = response.usage
    finish = response.choices[0].finish_reason if response.choices else None
    logger.info(
        "Model %s answered in %.1fs: %s prompt + %s completion tokens, finish=%s", model, seconds,
        usage.prompt_tokens if usage else "?", usage.completion_tokens if usage else "?", finish,
    )
    if finish == "length":
        logger.warning("Model %s stopped at the token limit, so its answer is cut off", model)

def _extract_json(content: str) -> dict:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        raise ValueError("no JSON object found")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    return data

def _normalize_weights(raw) -> dict:
    if not isinstance(raw, dict):
        return dict(DEFAULT_WEIGHTS)
    values = {key: max(0.0, _number(raw.get(key)) or 0.0) for key in CRITERIA}
    total = sum(values.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    weights = {key: round(value * 100 / total) for key, value in values.items()}
    weights[max(weights, key=weights.get)] += 100 - sum(weights.values())
    return weights

def _normalize_resume(data: dict, jd: dict, today: datetime.date, resume_text: str) -> dict:
    raw = data.get("ratings") if isinstance(data.get("ratings"), dict) else {}
    ratings = {key: _clamp(raw.get(key), 10) for key in CRITERIA}
    weights = jd["weights"]
    score = round(sum(weights[key] * ratings[key] for key in CRITERIA) / 10)

    positions = _work_history(data.get("positions"), today)
    relevant = [p for p in positions if p["relevant"]]
    relevant_years = _years(relevant)

    must_haves = _match_must_haves(jd["must_haves"], jd["deal_breakers"], data.get("must_haves"), resume_text, today)
    if jd["min_experience_years"]:
        must_haves.insert(0, _experience_check(jd, relevant, relevant_years))
    failed = [m for m in must_haves if m["met"] is False]
    failed_deal_breakers = [m["requirement"] for m in failed if m["deal_breaker"]]

    return {
        "candidate_name": _str(data.get("candidate_name")) or "Unknown",
        "email": _str(data.get("email")),
        "phone": _str(data.get("phone")),
        "current_title": _str(data.get("current_title")),
        "total_experience_years": _years(positions) if positions else None,
        "relevant_experience_years": relevant_years if positions else None,
        "positions": [{key: p[key] for key in ("title", "company", "period", "years", "relevant")} for p in positions],
        "score": score,
        "category": "Not Suitable" if failed_deal_breakers else categorize(score),
        "failed_must_haves": [m["requirement"] for m in failed],
        "failed_deal_breakers": failed_deal_breakers,
        "unverified_deal_breakers": [m["requirement"] for m in must_haves if m["deal_breaker"] and m["met"] is None],
        "must_haves": must_haves,
        "breakdown": {key: {"rating": ratings[key], "weight": weights[key]} for key in CRITERIA},
        "matched_skills": _str_list(data.get("matched_skills")),
        "missing_skills": _str_list(data.get("missing_skills")),
        "strengths": _str_list(data.get("strengths"))[:4],
        "concerns": _str_list(data.get("concerns"))[:4],
        "summary": _str(data.get("summary")) or "",
    }


def _work_history(raw, today: datetime.date) -> list[dict]:
    now = today.year * 12 + today.month - 1
    positions = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        start, end = _month(item.get("start"), now), _month(item.get("end"), now)
        if start is None or end is None:
            continue
        end = min(end, now)
        if start > end:
            continue
        positions.append({
            "title": _str(item.get("title")) or "Untitled position",
            "company": _str(item.get("company")),
            "start": start,
            "end": end,
            "period": f"{_month_label(start)} – {'Present' if end == now else _month_label(end)}",
            "years": round((end - start + 1) / 12, 1),
            "relevant": _bool(item.get("relevant")) is True,
        })
    return positions

def _month(value, now: int) -> int | None:
    text = (_str(value) or "").lower()
    if text in PRESENT_WORDS:
        return now
    match = re.match(r"(\d{4})(?:-(\d{1,2}))?", text)
    if not match:
        return None
    month = int(match.group(2) or 1)
    return int(match.group(1)) * 12 + month - 1 if 1 <= month <= 12 else None

def _month_label(month: int) -> str:
    return datetime.date(month // 12, month % 12 + 1, 1).strftime("%b %Y")


def _years(positions: list[dict]) -> float:
    months = set()
    for p in positions:
        months.update(range(p["start"], p["end"] + 1))
    return round(len(months) / 12, 1)

def _experience_check(jd: dict, relevant: list[dict], relevant_years: float) -> dict:
    jobs = "; ".join(f"{p['title']} ({p['period']})" for p in relevant)
    return {
        "requirement": jd["experience_requirement"],
        "met": relevant_years >= jd["min_experience_years"],
        "evidence": f"{relevant_years:g} years of relevant experience" + (f": {jobs}" if jobs else " found in resume"),
        "deal_breaker": False,
    }

def _match_must_haves(
    expected: list[str], deal_breakers: list[str], returned, resume_text: str, today: datetime.date
) -> list[dict]:
    items = [r for r in returned if isinstance(r, dict)] if isinstance(returned, list) else []
    by_text = {(_str(r.get("requirement")) or "").lower(): r for r in items}
    resume = _compact(resume_text)
    result = []
    for i, requirement in enumerate(expected):
        item = by_text.get(requirement.lower()) or (items[i] if len(items) == len(expected) else None)
        if not item:
            met, evidence = None, "The AI did not check this requirement. Check the resume manually."
        else:
            met, evidence = _bool(item.get("met")), _str(item.get("evidence"))
        if met is True and not _quoted_in_resume(evidence, resume):
            met = None
            evidence = f"Could not verify on the resume. The AI said: {evidence or 'no evidence given'}"
        if item and DEGREE_PATTERN.search(requirement):
            met, evidence = _check_degree_end(met, evidence, _str(item.get("degree_end")), resume_text, today)
        result.append(
            {"requirement": requirement, "met": met, "evidence": evidence, "deal_breaker": requirement in deal_breakers}
        )
    return result

def _check_degree_end(met, evidence, degree_end: str | None, resume_text: str, today: datetime.date):
    finished = _degree_finished(degree_end, resume_text, today)
    if finished is False and met is True:
        return None, f"The AI accepted a degree, but the date it gave ({degree_end}) is after today. Check the resume manually. {evidence}"
    if finished is False and met is None:
        return False, f"Degree not completed yet ({degree_end}). {evidence or ''}".strip()
    if finished is True and met is False and UNFINISHED_PATTERN.search(evidence or ""):
        return None, f"The AI said the degree is not completed, but it ended {degree_end}. Check the resume manually."
    if finished is None and degree_end and met is True:
        return None, f"Could not confirm the degree is completed (end date: {degree_end}). Check the resume. {evidence}"
    return met, evidence

def _degree_finished(degree_end: str | None, resume_text: str, today: datetime.date) -> bool | None:
    text = (degree_end or "").lower()
    match = re.search(r"(\d{4})(?:-(\d{1,2}))?", text)
    if not match or match.group(1) not in resume_text:
        return None
    if re.search(r"present|current|expected|pursuing|in progress|ongoing", text):
        return False
    year = int(match.group(1))
    if not match.group(2):
        return None if year == today.year else year < today.year
    now = today.year * 12 + today.month - 1
    end = _month(match.group(0), now)
    return None if end is None else end <= now

def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", text).lower())

def _quoted_in_resume(evidence: str | None, resume: str) -> bool:
    if not evidence:
        return False
    for part in re.split(r'[";|…]|\.\.\.', evidence):
        if len(_compact(part)) >= 6 and _compact(part) in resume:
            return True
    words = [w for w in re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", evidence).lower()) if len(w) > 2]
    return bool(words) and sum(w in resume for w in words) / len(words) >= 0.9

def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return {"true": True, "yes": True, "false": False, "no": False}.get(value.strip().lower())
    return None

def _clamp(value, limit: int) -> int:
    try:
        return max(0, min(limit, round(float(value))))
    except (TypeError, ValueError):
        return 0

def _number(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None

def _str(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in {"", "null", "none", "n/a"} else text
def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [s for s in (_str(v) for v in value) if s]
