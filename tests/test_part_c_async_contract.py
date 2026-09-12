import re
from pathlib import Path

from app.api.v1.endpoints import applications, matches
from app.schemas.job import AIJobAcceptedResponse


def _find_route(router, path: str):
    found = [
        route
        for route in router.routes
        if getattr(route, "path", None) == path
    ]
    assert len(found) == 1
    return found[0]


def test_match_explanation_is_durable_post_202():
    route = _find_route(
        matches.router,
        "/{id}/explanation",
    )
    assert route.methods == {"POST"}
    assert route.status_code == 202
    assert route.response_model is AIJobAcceptedResponse


def test_interview_prep_is_durable_post_202():
    route = _find_route(
        applications.router,
        "/{id}/interview-prep",
    )
    assert route.methods == {"POST"}
    assert route.status_code == 202
    assert route.response_model is AIJobAcceptedResponse


def test_http_boundaries_enqueue_instead_of_generate():
    root = Path(__file__).resolve().parents[1]
    match_source = (
        root / "backend/app/api/v1/endpoints/matches.py"
    ).read_text(encoding="utf-8")
    application_source = (
        root / "backend/app/api/v1/endpoints/applications.py"
    ).read_text(encoding="utf-8")
    assert "get_or_create_match_explanation(" not in match_source
    assert "get_or_create_interview_prep(" not in application_source
    assert "enqueue_match_explanation_generation(" in match_source
    assert "enqueue_interview_prep_generation(" in application_source


def test_mobile_generation_functions_return_job_contract():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")
    assert "export type AIJobAcceptedResponse = {" in source
    match_contract = re.search(
        r"export async function getMatchExplanation\("
        r"[\s\S]*?Promise<AIJobAcceptedResponse>"
        r"[\s\S]*?method: 'POST'",
        source,
    )
    prep_contract = re.search(
        r"export async function generateInterviewPrep\("
        r"[\s\S]*?Promise<AIJobAcceptedResponse>"
        r"[\s\S]*?method: 'POST'",
        source,
    )
    assert match_contract is not None
    assert prep_contract is not None


def test_part_c_worker_modules_are_preloaded():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "worker/worker.py"
    ).read_text(encoding="utf-8")
    assert '"tasks.match_explanation_generation",' in source
    assert '"tasks.interview_prep_generation",' in source
