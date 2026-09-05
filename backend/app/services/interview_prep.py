"""
Grounded AI Interview Preparation Service

Generates candidate interview preparation using Google Gemini structured
output. The generation is strictly grounded in canonical persisted profile,
internship, application, interview, and match data.

No database mutation is performed. Successful results are cached in Redis
using a content-derived context hash.
"""

import hashlib
import json
from typing import Literal
from uuid import UUID

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.match import MatchRepository
from app.repositories.matching_data import MatchingDataRepository
from app.schemas.interview_prep import InterviewPrepResponse
from app.services.ai_quota import FEATURE_INTERVIEW_PREP
from app.services.ai_quota_integration import (
    release_sync_ai_quota,
    reserve_sync_ai_quota,
    settle_sync_ai_quota,
)
from app.services.ai_telemetry import (
    ai_telemetry_context,
    create_tracked_gemini_client,
)

CACHE_VERSION = "v1"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


class LLMInterviewPrep(BaseModel):
    """Structured Gemini output without server-owned identifiers."""

    preparation_summary: str
    likely_questions: list[str] = Field(min_length=3, max_length=6)
    focus_areas: list[str] = Field(min_length=1, max_length=6)
    strengths_to_highlight: list[str] = Field(min_length=1, max_length=6)
    questions_to_ask: list[str] = Field(min_length=2, max_length=5)


def _normalize_locale(value: str) -> Literal["en", "tr", "ar"]:
    normalized = (value or "en").strip().lower()

    if normalized not in {"en", "tr", "ar"}:
        return "en"

    return normalized  # type: ignore[return-value]


def _get_redis_client() -> Redis:
    redis_url = (settings.REDIS_URL or "").strip()

    if not redis_url:
        raise ValueError("Redis configuration is unavailable.")

    return Redis.from_url(
        redis_url,
        decode_responses=True,
    )


def _serialize_entries(entries: list[object]) -> list[str]:
    values: list[str] = []

    for entry in entries:
        raw = {
            key: value
            for key, value in vars(entry).items()
            if not key.startswith("_")
            and value is not None
            and key not in {"id", "student_id", "created_at", "updated_at"}
        }

        if raw:
            values.append(
                ", ".join(
                    f"{key}: {value}"
                    for key, value in raw.items()
                )
            )

    return values


def get_or_create_interview_prep(
    *,
    db: Session,
    application: object,
    internship: object,
    user_id: UUID,
    content_locale: str = "en",
) -> InterviewPrepResponse:
    """
    Return cached or newly generated grounded interview preparation.

    Caller must already enforce candidate ownership of the application.
    Requires a scheduled application currently in the interviewing stage.
    """

    locale = _normalize_locale(content_locale)

    if getattr(application, "status", None) != "interviewing":
        raise ValueError(
            "Interview preparation is available only while the application "
            "is in the interviewing stage."
        )

    scheduled_at = getattr(
        application,
        "interview_scheduled_at",
        None,
    )

    if scheduled_at is None:
        raise ValueError(
            "Interview preparation requires a scheduled interview."
        )

    profile = MatchingDataRepository.get_profile_by_user_id(
        db,
        user_id,
    )

    if profile is None:
        raise ValueError("Candidate profile is unavailable.")

    candidate_skills = (
        MatchingDataRepository.get_skill_names_for_student(
            db,
            profile.id,
        )
    )

    education_entries = _serialize_entries(
        MatchingDataRepository.get_education_for_student(
            db,
            profile.id,
        )
    )

    experience_entries = _serialize_entries(
        MatchingDataRepository.get_experience_for_student(
            db,
            profile.id,
        )
    )

    project_entries = _serialize_entries(
        MatchingDataRepository.get_projects_for_student(
            db,
            profile.id,
        )
    )

    match = next(
        (
            candidate_match
            for candidate_match
            in MatchRepository.get_matches_by_student_id(
                db,
                profile.id,
            )
            if candidate_match.internship_id
            == getattr(internship, "id", None)
        ),
        None,
    )

    raw_gap = (
        match.skill_gap_analysis
        if match is not None
        and isinstance(match.skill_gap_analysis, dict)
        else {}
    )

    matching_skills = raw_gap.get("matching_skills", [])
    missing_skills = raw_gap.get("missing_skills", [])

    if not isinstance(matching_skills, list):
        matching_skills = []

    if not isinstance(missing_skills, list):
        missing_skills = []

    context = {
        "application_id": str(getattr(application, "id")),
        "scheduled_at": scheduled_at.isoformat(),
        "interview_mode": getattr(
            application,
            "interview_mode",
            None,
        ),
        "interview_location": getattr(
            application,
            "interview_location",
            None,
        ),
        "interview_message": getattr(
            application,
            "interview_message",
            None,
        ),
        "locale": locale,
        "candidate_name": profile.full_name,
        "candidate_headline": profile.headline,
        "candidate_skills": candidate_skills,
        "education": education_entries,
        "experience": experience_entries,
        "projects": project_entries,
        "internship_title": getattr(internship, "title", None),
        "internship_company": getattr(internship, "company", None),
        "internship_location": getattr(internship, "location", None),
        "internship_work_type": getattr(
            internship,
            "work_type",
            None,
        ),
        "internship_description": getattr(
            internship,
            "description",
            None,
        ),
        "required_skills": (
            getattr(internship, "required_skills", None) or []
        ),
        "preferred_skills": (
            getattr(internship, "preferred_skills", None) or []
        ),
        "overall_match_score": (
            match.overall_score
            if match is not None
            else None
        ),
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
    }

    context_json = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    context_hash = hashlib.sha256(
        context_json.encode("utf-8")
    ).hexdigest()

    cache_key = (
        "internmatch:interview-prep:"
        f"{CACHE_VERSION}:"
        f"{getattr(application, 'id')}:"
        f"{locale}:"
        f"{context_hash}"
    )

    redis_client = None

    try:
        redis_client = _get_redis_client()
        cached = redis_client.get(cache_key)

        if cached:
            cached_payload = LLMInterviewPrep.model_validate_json(
                cached
            )

            return InterviewPrepResponse(
                application_id=getattr(application, "id"),
                interview_scheduled_at=scheduled_at,
                **cached_payload.model_dump(),
            )
    except Exception:
        # Redis is an optimization boundary only.
        # Generation remains available if cache infrastructure is unavailable.
        redis_client = None

    if not (settings.GEMINI_API_KEY or "").strip():
        raise ValueError(
            "Gemini interview preparation is unavailable."
        )

    system_prompt = f"""
You are the grounded AI interview preparation assistant for InternMatch AI.

Target response locale: {locale}

Your task is to prepare a student for ONE scheduled internship interview.

STRICT GROUNDING RULES:
1. Use ONLY the factual candidate, internship, match, and interview data
   provided in the user content.
2. Never invent candidate skills, work experience, education, projects,
   employer facts, interview format, or company details.
3. The matching_skills and missing_skills lists are authoritative when present.
4. "likely_questions" are preparation suggestions, NOT claims about questions
   the employer will definitely ask.
5. Focus questions on the actual internship requirements and the candidate's
   actual background.
6. strengths_to_highlight must contain only strengths supported by the supplied
   candidate or match data.
7. focus_areas should prioritize genuine requirements or known missing skills.
8. questions_to_ask should be professional questions the candidate may ask the
   interviewer about the role, team, expectations, or internship.
9. Keep preparation_summary concise and practical.
10. Return structured JSON only through the provided schema.
""".strip()

    user_content = (
        "Prepare this candidate for the scheduled interview using only "
        "the following canonical context:\n\n"
        + context_json
    )

    application_id = getattr(application, "id")

    quota_reservation = reserve_sync_ai_quota(
        db,
        user_id=user_id,
        feature_key=FEATURE_INTERVIEW_PREP,
        idempotency_key=(
            f"{FEATURE_INTERVIEW_PREP}:"
            f"application:{application_id}:{locale}:{context_hash}"
        ),
        request_fingerprint=(
            f"application:{application_id}:{locale}:{context_hash}"
        ),
    )
    quota_operation_id = quota_reservation["operation"].id

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        client = create_tracked_gemini_client(genai.Client, 'interview_prep',
            api_key=settings.GEMINI_API_KEY,
        )

        with ai_telemetry_context(
            user_id=user_id,
            quota_operation_id=quota_operation_id,
        ):
            response = client.models.generate_content(
                model=settings.LLM_MODEL_NAME,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_json_schema=LLMInterviewPrep.model_json_schema(),
                ),
            )

        raw_text = getattr(response, "text", None)

        if (
            not isinstance(raw_text, str)
            or not raw_text.strip()
        ):
            raise ValueError(
                "Gemini returned empty interview preparation."
            )

        try:
            generated = LLMInterviewPrep.model_validate_json(
                raw_text
            )
        except Exception as exc:
            raise ValueError(
                "Gemini returned invalid structured interview preparation."
            ) from exc

    except Exception:
        db.rollback()

        release_sync_ai_quota(
            db,
            operation_id=quota_operation_id,
            reason="provider_or_validation_failure",
        )
        db.commit()
        raise

    try:
        settle_sync_ai_quota(
            db,
            operation_id=quota_operation_id,
        )
        db.commit()
    except Exception:
        db.rollback()

        release_sync_ai_quota(
            db,
            operation_id=quota_operation_id,
            reason="settlement_failure",
        )
        db.commit()
        raise

    if redis_client is not None:
        try:
            redis_client.set(
                cache_key,
                generated.model_dump_json(),
                ex=CACHE_TTL_SECONDS,
            )
        except Exception:
            pass

    return InterviewPrepResponse(
        application_id=getattr(application, "id"),
        interview_scheduled_at=scheduled_at,
        **generated.model_dump(),
    )
