"""
Unit & Integration Regression Tests for Candidate Skills Semantics & Invalidation Rules.
Tests manual skill management, validation limits, embedding invalidation, user isolation,
and CV-extraction merge semantics.
"""

from uuid import uuid4

import pytest
from app.db.models import Skill, StudentProfile, StudentSkill
from app.repositories.candidate_profile_write import replace_candidate_profile_from_extraction
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.cv_profile_extraction import (
    ExtractedCandidateProfile,
    ExtractedPreferences,
    ExtractedSkill,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


def test_1_authenticated_candidate_can_set_skills_manually(client: TestClient):
    """Test 1: Authenticated candidate can manually set and update their skills."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    payload = {
        "full_name": "Skill Tester",
        "headline": "Full-Stack Dev",
        "skills": ["Python", "FastAPI", "React"],
    }
    response = client.put(
        "/api/v1/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert sorted(data["skills"]) == ["FastAPI", "Python", "React"]


def test_2_unauthenticated_user_cannot_update_skills(client: TestClient):
    """Test 2: Unauthenticated user cannot update skills (returns 401 UNAUTHORIZED)."""
    payload = {
        "full_name": "Anon User",
        "skills": ["Python"],
    }
    response = client.put("/api/v1/profile", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_3_user_isolation_is_preserved(client: TestClient):
    """Test 3: Updating User A skills does not modify or leak into User B skills."""
    user_a = uuid4()
    user_b = uuid4()
    token_a = f"valid-user-{user_a}"
    token_b = f"valid-user-{user_b}"

    # Set User A skills
    client.put(
        "/api/v1/profile",
        json={"full_name": "User A", "skills": ["Python", "Docker"]},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Set User B skills
    client.put(
        "/api/v1/profile",
        json={"full_name": "User B", "skills": ["Rust", "Kubernetes"]},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Fetch User A profile
    res_a = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token_a}"})
    assert sorted(res_a.json()["skills"]) == ["Docker", "Python"]

    # Fetch User B profile
    res_b = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token_b}"})
    assert sorted(res_b.json()["skills"]) == ["Kubernetes", "Rust"]


def test_4_duplicate_case_insensitive_skills_normalize_correctly(client: TestClient):
    """Test 4: Duplicates with different casing or leading/trailing whitespace collapse."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    payload = {
        "full_name": "Case Tester",
        "skills": ["Python", " python ", "PYTHON", "  FastAPI  ", "fastapi"],
    }
    response = client.put(
        "/api/v1/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    skills = response.json()["skills"]
    assert len(skills) == 2
    assert sorted([s.lower() for s in skills]) == ["fastapi", "python"]


def test_5_blank_skill_rejected_with_validation_error(client: TestClient):
    """Test 5: Blank / whitespace-only skill items are rejected with 422 Unprocessable Entity."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    payload = {
        "full_name": "Blank Tester",
        "skills": ["Python", "   ", "React"],
    }
    response = client.put(
        "/api/v1/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_6_max_skill_count_exceeded_rejected(client: TestClient):
    """Test 6: Submitting > 50 skills is rejected with 422 Unprocessable Entity."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    payload = {
        "full_name": "Overloaded Tester",
        "skills": [f"Skill_{i}" for i in range(51)],
    }
    response = client.put(
        "/api/v1/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_7_overlong_skill_name_rejected(client: TestClient):
    """Test 7: Submitting skill name > 80 characters is rejected with 422."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    overlong_skill = "A" * 81
    payload = {
        "full_name": "Long Skill Tester",
        "skills": ["Python", overlong_skill],
    }
    response = client.put(
        "/api/v1/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_8_manual_skill_add_invalidates_embedding(client: TestClient):
    """Test 8: Adding a new manual skill clears existing summary_embedding."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    # Create profile with initial skills
    client.put(
        "/api/v1/profile",
        json={"full_name": "Embed Tester", "skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Set mock summary embedding
    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    StudentProfileRepository.set_summary_embedding(db, prof, [0.5] * 1536)
    db.commit()
    db.close()

    # Add a new skill
    client.put(
        "/api/v1/profile",
        json={"full_name": "Embed Tester", "skills": ["Python", "FastAPI"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.summary_embedding is None
    db_check.close()


def test_9_manual_skill_removal_invalidates_embedding(client: TestClient):
    """Test 9: Removing a manual skill clears existing summary_embedding."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    # Create profile with 2 skills
    client.put(
        "/api/v1/profile",
        json={"full_name": "Removal Tester", "skills": ["Python", "FastAPI"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Set mock summary embedding
    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    StudentProfileRepository.set_summary_embedding(db, prof, [0.5] * 1536)
    db.commit()
    db.close()

    # Remove one skill
    client.put(
        "/api/v1/profile",
        json={"full_name": "Removal Tester", "skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.summary_embedding is None
    db_check.close()


def test_10_semantically_identical_normalized_skills_preserve_embedding(client: TestClient):
    """Test 10: Submitting effectively identical skills preserves embedding."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    client.put(
        "/api/v1/profile",
        json={"full_name": "Identical Tester", "skills": ["Python", "FastAPI"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    mock_vec = [0.77] * 1536
    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    StudentProfileRepository.set_summary_embedding(db, prof, mock_vec)
    db.commit()
    db.close()

    # Submit same skills with different casing & whitespace
    client.put(
        "/api/v1/profile",
        json={"full_name": "Identical Tester", "skills": [" python ", "FASTAPI"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.summary_embedding == mock_vec
    db_check.close()


def test_11_social_link_only_profile_update_preserves_embedding(client: TestClient):
    """Test 11: Updating only social links preserves summary_embedding."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    client.put(
        "/api/v1/profile",
        json={
            "full_name": "Social Tester",
            "skills": ["Python"],
            "preferences": {"linkedin_url": "https://linkedin.com/in/initial"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    mock_vec = [0.88] * 1536
    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    StudentProfileRepository.set_summary_embedding(db, prof, mock_vec)
    db.commit()
    db.close()

    # Update only social links
    client.put(
        "/api/v1/profile",
        json={
            "full_name": "Social Tester",
            "skills": ["Python"],
            "preferences": {
                "linkedin_url": "https://linkedin.com/in/updated",
                "github_url": "https://github.com/updated",
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.summary_embedding == mock_vec
    db_check.close()


def test_12_semantic_preference_update_invalidates_embedding(client: TestClient):
    """Test 12: Updating semantic preferences clears summary_embedding."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    client.put(
        "/api/v1/profile",
        json={
            "full_name": "Pref Tester",
            "preferences": {"work_types": ["remote"]},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    mock_vec = [0.99] * 1536
    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    StudentProfileRepository.set_summary_embedding(db, prof, mock_vec)
    db.commit()
    db.close()

    # Update semantic preference
    client.put(
        "/api/v1/profile",
        json={
            "full_name": "Pref Tester",
            "preferences": {"work_types": ["onsite"]},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.summary_embedding is None
    db_check.close()


def test_13_cv_extraction_merges_with_existing_skills():
    """Test 13: CV extraction merges newly extracted skills with existing candidate skills."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        # Create initial profile with existing manual skill
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="CV Merge Student"
        )
        StudentProfileRepository.sync_student_skills(db, prof.id, ["Docker", "Python"])
        db.commit()

        # Simulate CV extraction with overlapping and new skills
        extracted = ExtractedCandidateProfile(
            full_name="CV Merge Student",
            skills=[
                ExtractedSkill(name="Python"),
                ExtractedSkill(name="FastAPI"),
                ExtractedSkill(name="PostgreSQL"),
            ],
            education=[],
            experience=[],
            projects=[],
        )

        replace_candidate_profile_from_extraction(
            db,
            user_id=user_id,
            cv_storage_path="cvs/merge_cv.pdf",
            extracted=extracted,
        )
        db.commit()

        # CV extraction adds/updates CV evidence while preserving manual skills.
        skills = MatchingDataRepository.get_skill_names_for_student(db, prof.id)
        assert sorted(skills) == ["Docker", "FastAPI", "PostgreSQL", "Python"]
    finally:
        db.close()


def test_14_cv_extraction_does_not_duplicate_existing_skills():
    """Test 14: CV extraction does not duplicate existing skills."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Dedup Student"
        )
        StudentProfileRepository.sync_student_skills(db, prof.id, ["Python", "FastAPI"])
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Dedup Student",
            skills=[
                ExtractedSkill(name=" python "),
                ExtractedSkill(name="FASTAPI"),
            ],
            education=[],
            experience=[],
            projects=[],
        )

        replace_candidate_profile_from_extraction(
            db,
            user_id=user_id,
            cv_storage_path="cvs/dedup_cv.pdf",
            extracted=extracted,
        )
        db.commit()

        # Verify skills count is still 2 without duplicates
        skills = MatchingDataRepository.get_skill_names_for_student(db, prof.id)
        assert len(skills) == 2
        assert sorted([s.lower() for s in skills]) == ["fastapi", "python"]
    finally:
        db.close()


def test_15_extracted_skills_preserve_manual_skills():
    """Test 15: Newly extracted CV skills preserve existing manual skills."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        # Candidate manually adds a skill
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Surviving Skill Student"
        )
        StudentProfileRepository.sync_student_skills(
            db, prof.id, ["SpecializedManualSkill", "Python"]
        )
        db.commit()

        # Later CV upload extracts standard skills only
        extracted = ExtractedCandidateProfile(
            full_name="Surviving Skill Student",
            skills=[
                ExtractedSkill(name="Python"),
                ExtractedSkill(name="React"),
            ],
            education=[],
            experience=[],
            projects=[],
        )

        replace_candidate_profile_from_extraction(
            db,
            user_id=user_id,
            cv_storage_path="cvs/later_cv.pdf",
            extracted=extracted,
        )
        db.commit()

        skills = MatchingDataRepository.get_skill_names_for_student(db, prof.id)
        assert sorted(skills) == ["Python", "React", "SpecializedManualSkill"]
    finally:
        db.close()


def test_16_get_profile_returns_resulting_skills_correctly(client: TestClient):
    """Test 16: GET /api/v1/profile returns skills accurately in deterministic format."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    client.put(
        "/api/v1/profile",
        json={"full_name": "Get Profile Tester", "skills": ["TypeScript", "Next.js", "C++"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["skills"] == ["C++", "Next.js", "TypeScript"]


def test_17_cv_path_semantics_remain_preserved(client: TestClient):
    """Test 17: CV storage path is preserved when updating manual skills."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    # Initial profile with cv_storage_path
    client.put(
        "/api/v1/profile",
        json={
            "full_name": "CV Path Tester",
            "cv_storage_path": "cvs/my_persisted_cv.pdf",
            "skills": ["Python"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Update skills without changing cv_storage_path
    response = client.put(
        "/api/v1/profile",
        json={"full_name": "CV Path Tester", "skills": ["Python", "FastAPI"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    db = TestingSessionLocal()
    prof = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    assert prof.cv_storage_path == "cvs/my_persisted_cv.pdf"
    db.close()


def test_18_avatar_semantics_remain_preserved(client: TestClient):
    """Test 18: Avatar storage path is preserved when updating manual skills."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    # Create profile and assign avatar
    client.put(
        "/api/v1/profile",
        json={"full_name": "Avatar Tester", "skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    db = TestingSessionLocal()
    StudentProfileRepository.update_avatar_storage_path(
        db, user_id=user_id, avatar_storage_path="avatars/user_pic.jpg"
    )
    db.commit()
    db.close()

    # Update skills manually
    response = client.put(
        "/api/v1/profile",
        json={"full_name": "Avatar Tester", "skills": ["Python", "React"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    db_check = TestingSessionLocal()
    prof_check = StudentProfileRepository.get_by_user_id(db_check, user_id=user_id)
    assert prof_check.avatar_storage_path == "avatars/user_pic.jpg"
    db_check.close()


def test_19_cv_extraction_preserves_manual_metadata_and_updates_semantic_preferences():
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            user_id=user_id,
            full_name='Preference Test',
            headline='Engineer',
            preferences={
                'department': 'Computer Engineering',
                'linkedin_url': 'https://linkedin.com/in/test',
                'github_url': 'https://github.com/test',
                'portfolio_url': 'https://example.com',
                'work_types': ['internship'],
                'desired_locations': ['Istanbul'],
                'target_roles': ['Backend Engineer'],
            },
        )
        db.add(profile)
        db.flush()

        manual_skill = Skill(name='ManualOnlySkill')
        db.add(manual_skill)
        db.flush()
        db.add(
            StudentSkill(
                student_id=profile.id,
                skill_id=manual_skill.id,
                proficiency_level='intermediate',
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name='Preference Test',
            headline='Engineer',
            skills=[ExtractedSkill(name='Python')],
            preferences=ExtractedPreferences(
                work_types=[],
                desired_locations=['Ankara'],
                target_roles=[],
            ),
        )

        updated = replace_candidate_profile_from_extraction(
            db=db,
            user_id=user_id,
            cv_storage_path='candidate/test.pdf',
            extracted=extracted,
        )
        db.commit()
        db.refresh(updated)

        assert updated.preferences['department'] == 'Computer Engineering'
        assert updated.preferences['linkedin_url'] == 'https://linkedin.com/in/test'
        assert updated.preferences['github_url'] == 'https://github.com/test'
        assert updated.preferences['portfolio_url'] == 'https://example.com'
        assert updated.preferences['work_types'] == ['internship']
        assert updated.preferences['desired_locations'] == ['Ankara']
        assert updated.preferences['target_roles'] == ['Backend Engineer']

        skills = MatchingDataRepository.get_skill_names_for_student(db, updated.id)
        assert sorted(skills) == ['ManualOnlySkill', 'Python']
    finally:
        db.close()
