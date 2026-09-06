from unittest.mock import MagicMock
from uuid import uuid4

from app.repositories.match import MatchRepository
from app.services.ai_telemetry import (
    TELEMETRY_LOCK_TIMEOUT_MS,
    _apply_telemetry_lock_timeout,
)
from sqlalchemy.dialects import postgresql


def test_telemetry_lock_timeout_is_applied_on_postgres() -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db.get_bind.return_value = bind

    _apply_telemetry_lock_timeout(db)

    db.execute.assert_called_once()

    sql = str(
        db.execute.call_args.args[0]
    )

    assert "SET LOCAL lock_timeout" in sql
    assert str(TELEMETRY_LOCK_TIMEOUT_MS) in sql


def test_telemetry_lock_timeout_is_skipped_off_postgres() -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    db.get_bind.return_value = bind

    _apply_telemetry_lock_timeout(db)

    db.execute.assert_not_called()


def test_targeted_match_lookup_filters_student_and_internship() -> None:
    student_id = uuid4()
    internship_id = uuid4()

    db = MagicMock()
    db.scalar.return_value = None

    result = (
        MatchRepository.get_match_by_student_and_internship(
            db,
            student_id=student_id,
            internship_id=internship_id,
        )
    )

    assert result is None
    db.scalar.assert_called_once()

    statement = db.scalar.call_args.args[0]

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    normalized = " ".join(
        sql.split()
    )

    assert "matches.student_id" in normalized
    assert "matches.internship_id" in normalized
    assert str(student_id) in normalized
    assert str(internship_id) in normalized


def test_ai_grounding_context_uses_one_postgres_round_trip():
    from app.repositories.matching_data import (
        MatchingDataRepository,
    )

    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db.get_bind.return_value = bind

    db.execute.return_value.mappings.return_value.one.return_value = {
        "skills": ["Go", "Python"],
        "education_entries": [
            "B.S. Computer Science at Tech University (2021-2025)"
        ],
        "experience_entries": [
            "Developer at Example Labs: Backend work"
        ],
        "project_entries": [
            "Alpha Platform (Python): API project"
        ],
    }

    result = (
        MatchingDataRepository
        .get_ai_grounding_context(
            db,
            uuid4(),
        )
    )

    assert result["skills"] == [
        "Go",
        "Python",
    ]
    assert result["education_entries"] == [
        "B.S. Computer Science at Tech University (2021-2025)"
    ]
    assert result["experience_entries"] == [
        "Developer at Example Labs: Backend work"
    ]
    assert result["project_entries"] == [
        "Alpha Platform (Python): API project"
    ]

    db.execute.assert_called_once()

    statement = db.execute.call_args.args[0]
    sql = str(statement)

    assert "student_skills" in sql
    assert "education_entries" in sql
    assert "experience_entries" in sql
    assert "project_entries" in sql
