from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_ai_consent_service_is_explicit_and_names_providers():
    source = read("apps/mobile/src/services/aiConsent.ts")

    assert "Google Gemini" in source
    assert "OpenAI" in source
    assert "Allow AI Processing" in source
    assert "Not Now" in source
    assert "cancelable: false" in source
    assert "ensureAIProcessingConsent" in source
    assert "granted_at" in source


def test_ai_triggering_api_operations_are_fail_closed():
    source = read("apps/mobile/src/services/api.ts")

    expected_functions = [
        "uploadCV",
        "calculateMatches",
        "getMatchExplanation",
        "generateInterviewPrep",
        "generateApplication",
        "generateEmployerInternshipDescription",
        "createEmployerInternship",
        "updateEmployerInternship",
        "compareEmployerShortlist",
        "getEmployerCandidateInsight",
        "getEmployerInterviewKit",
        "submitApplication",
    ]

    assert "AI_CONSENT_REQUIRED" in source

    for name in expected_functions:
        start = source.index(
            f"export async function {name}"
        )
        next_export = source.find(
            "export async function ",
            start + 1,
        )
        block = (
            source[start:]
            if next_export == -1
            else source[start:next_export]
        )

        assert (
            "await requireAIProcessingConsent();"
            in block
        ), name


def test_blocked_employers_are_filtered_from_core_lists():
    api = read("apps/mobile/src/services/api.ts")
    safety = read(
        "apps/mobile/src/services/contentSafety.ts"
    )

    assert "blockEmployerCompany" in safety
    assert "filterBlockedInternships" in api
    assert "filterBlockedMatches" in api
    assert "filterBlockedSavedInternships" in api


def test_opportunity_detail_exposes_report_and_block_controls():
    source = read(
        "apps/mobile/src/screens/InternshipDetailScreen.js"
    )

    assert "handleReportOpportunity" in source
    assert "handleBlockEmployer" in source
    assert "Report Opportunity" in source
    assert "Block Employer" in source
    assert "flag-outline" in source
    assert "ban-outline" in source
    assert "internmatch@vertexintelligent.com" in source
