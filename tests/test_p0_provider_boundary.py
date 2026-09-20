import ast
from pathlib import Path

ENDPOINT_SOURCE = Path(
    "backend/app/api/v1/endpoints/internships.py"
).read_text(encoding="utf-8")


def _brokered_cv_block() -> str:
    """
    Extract the secure brokered CV route directly from the Python AST.

    Do not use the removed legacy /cv route as an end marker.
    A3 intentionally deletes that legacy signed-URL endpoint.
    """
    tree = ast.parse(ENDPOINT_SOURCE)

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name
        == "download_employer_applicant_cv_content"
    ]

    assert len(matches) == 1

    node = matches[0]

    assert node.end_lineno is not None

    start_line = node.lineno

    if node.decorator_list:
        start_line = min(
            [start_line]
            + [
                decorator.lineno
                for decorator in node.decorator_list
            ]
        )

    lines = ENDPOINT_SOURCE.splitlines()

    return "\n".join(
        lines[start_line - 1 : node.end_lineno]
    )

def test_brokered_cv_route_requires_authenticated_employer():
    block = _brokered_cv_block()

    assert "Depends(require_employer_user)" in block


def test_brokered_cv_route_reauthorizes_listing_and_application():
    block = _brokered_cv_block()

    assert (
        "ApplicationRepository.get_applicant_detail_for_employer("
        in block
    )
    assert "internship_id=id" in block
    assert "application_id=application_id" in block
    assert "employer_user_id=current_user.user_id" in block
    assert 'application.status == "saved"' in block


def test_brokered_cv_route_never_returns_storage_provider_url():
    block = _brokered_cv_block()

    assert "download_candidate_cv(" in block
    assert "Response(" in block

    assert "generate_candidate_cv_signed_url" not in block
    assert "create_signed_url" not in block
    assert "cv_url=" not in block
    assert "signed_url" not in block
    assert "supabase.co" not in block


def test_brokered_cv_route_disables_client_caching():
    block = _brokered_cv_block()

    assert '"Cache-Control": "private, no-store, max-age=0"' in block
    assert '"Pragma": "no-cache"' in block
    assert '"X-Content-Type-Options": "nosniff"' in block
    assert '"Referrer-Policy": "no-referrer"' in block


def test_mobile_cv_flow_uses_brokered_authenticated_download():
    api_source = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")

    screen_source = Path(
        "apps/mobile/src/screens/EmployerApplicantDetailScreen.js"
    ).read_text(encoding="utf-8")

    assert "downloadEmployerApplicantCV(" in api_source
    assert "/cv/content" in api_source
    assert "FileSystem.downloadAsync(" in api_source
    assert "Authorization: 'Bearer ' + token" in api_source

    assert "downloadEmployerApplicantCV(" in screen_source
    assert "Sharing.shareAsync(" in screen_source
    assert "deleteTemporaryEmployerApplicantCV(" in screen_source


def test_mobile_employer_cv_flow_has_no_provider_url_contract():
    api_source = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")

    screen_source = Path(
        "apps/mobile/src/screens/EmployerApplicantDetailScreen.js"
    ).read_text(encoding="utf-8")

    helper_start = api_source.index(
        "export async function downloadEmployerApplicantCV("
    )
    helper_end = api_source.index(
        "export async function deleteTemporaryEmployerApplicantCV(",
        helper_start,
    )

    helper = api_source[helper_start:helper_end]

    assert "supabase.co" not in helper
    assert "create_signed_url" not in helper
    assert "signed_url" not in helper
    assert "cv_url" not in helper

    assert "getEmployerApplicantCV(" not in api_source
    assert "access?.cv_url" not in screen_source
    assert "Linking.openURL(" not in screen_source


def test_mobile_cv_temporary_file_cleanup_is_cache_scoped():
    api_source = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")

    assert "FileSystem.cacheDirectory" in api_source
    assert "internmatch-cv-" in api_source
    assert "deleteTemporaryEmployerApplicantCV(" in api_source
    assert (
        "!uri.startsWith(`${cacheDirectory}internmatch-cv-`)"
        in api_source
    )


def test_mobile_cv_security_copy_no_longer_promises_signed_link():
    screen_source = Path(
        "apps/mobile/src/screens/EmployerApplicantDetailScreen.js"
    ).read_text(encoding="utf-8")

    assert (
        "A secure link is created only when you open"
        not in screen_source
    )
    assert "no storage-provider link is exposed" in screen_source



def test_legacy_signed_cv_backend_contract_is_fully_removed():
    endpoint_source = Path(
        "backend/app/api/v1/endpoints/internships.py"
    ).read_text(encoding="utf-8")

    schema_source = Path(
        "backend/app/schemas/application.py"
    ).read_text(encoding="utf-8")

    storage_source = Path(
        "backend/app/services/cv_storage.py"
    ).read_text(encoding="utf-8")

    assert (
        '"/{id}/applicants/{application_id}/cv",'
        not in endpoint_source
    )

    assert (
        '"/{id}/applicants/{application_id}/cv/content"'
        in endpoint_source
    )

    assert "EmployerCVAccessResponse" not in endpoint_source
    assert "EmployerCVAccessResponse" not in schema_source

    assert "generate_candidate_cv_signed_url" not in endpoint_source
    assert "generate_candidate_cv_signed_url" not in storage_source

    assert "CV_SIGNED_URL_EXPIRY_SECONDS" not in endpoint_source
    assert "CV_SIGNED_URL_EXPIRY_SECONDS" not in storage_source

    assert "create_signed_url(" not in storage_source


def test_cv_storage_retains_private_byte_download_only():
    storage_source = Path(
        "backend/app/services/cv_storage.py"
    ).read_text(encoding="utf-8")

    endpoint_source = Path(
        "backend/app/api/v1/endpoints/internships.py"
    ).read_text(encoding="utf-8")

    assert "download_candidate_cv" in storage_source
    assert "download_candidate_cv(" in endpoint_source

    assert (
        '"Cache-Control": "private, no-store, max-age=0"'
        in endpoint_source
    )

    assert '"Referrer-Policy": "no-referrer"' in endpoint_source



def test_compliance_evidence_user_facing_provider_urls_are_removed():
    endpoint_source = Path(
        "backend/app/api/v1/endpoints/employer_compliance.py"
    ).read_text(encoding="utf-8")

    mobile_api = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")

    mobile_screen = Path(
        "apps/mobile/src/screens/EmployerComplianceScreen.js"
    ).read_text(encoding="utf-8")

    admin_api = Path(
        "apps/admin/lib/api.ts"
    ).read_text(encoding="utf-8")

    admin_page = Path(
        "apps/admin/app/compliance/page.tsx"
    ).read_text(encoding="utf-8")

    admin_types = Path(
        "apps/admin/lib/types.ts"
    ).read_text(encoding="utf-8")

    assert "/evidence/{evidence_id}/content" in endpoint_source
    assert "evidence_url" not in endpoint_source

    assert "downloadEmployerComplianceEvidence(" in mobile_api
    assert "/content" in mobile_api
    assert "Authorization: 'Bearer ' + token" in mobile_api
    assert "access.evidence_url" not in mobile_screen
    assert "Sharing.shareAsync(" in mobile_screen

    assert "downloadComplianceEvidence(" in admin_api
    assert "Authorization: 'Bearer ' + token" in admin_api
    assert "access.evidence_url" not in admin_page
    assert "URL.createObjectURL(blob)" in admin_page
    assert "ComplianceEvidenceAccessResponse" not in admin_types


def test_compliance_content_endpoints_disable_client_caching():
    endpoint_source = Path(
        "backend/app/api/v1/endpoints/employer_compliance.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(endpoint_source)

    expected_functions = {
        "download_my_compliance_evidence_content",
        "download_admin_compliance_evidence_content",
    }

    found = {
        node.name: node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name in expected_functions
    }

    assert set(found) == expected_functions

    for function_name in expected_functions:
        function_node = found[function_name]

        constants = {
            child.value
            for child in ast.walk(function_node)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
        }

        assert "Cache-Control" in constants
        assert "private, no-store, max-age=0" in constants

        assert "Pragma" in constants
        assert "no-cache" in constants

        assert "X-Content-Type-Options" in constants
        assert "nosniff" in constants

        assert "Referrer-Policy" in constants
        assert "no-referrer" in constants

        assert any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "Response"
            for child in ast.walk(function_node)
        )


def test_compliance_private_storage_has_direct_byte_downloader():
    storage_source = Path(
        "backend/app/services/employer_compliance_storage.py"
    ).read_text(encoding="utf-8")

    assert "def download_compliance_evidence(" in storage_source
    assert ".download(" in storage_source



def test_compliance_signed_url_capability_is_fully_removed():
    storage_source = Path(
        "backend/app/services/employer_compliance_storage.py"
    ).read_text(encoding="utf-8")

    endpoint_source = Path(
        "backend/app/api/v1/endpoints/employer_compliance.py"
    ).read_text(encoding="utf-8")

    assert (
        "generate_compliance_evidence_signed_url"
        not in storage_source
    )

    assert (
        "COMPLIANCE_SIGNED_URL_EXPIRY_SECONDS"
        not in storage_source
    )

    assert "create_signed_url(" not in storage_source

    assert (
        "generate_compliance_evidence_signed_url"
        not in endpoint_source
    )

    assert "evidence_url" not in endpoint_source

    assert "download_compliance_evidence(" in endpoint_source



def test_avatar_broker_and_local_cache_provider_boundary():
    from pathlib import Path

    storage_source = Path(
        "backend/app/services/avatar_storage.py"
    ).read_text(encoding="utf-8")

    profile_source = Path(
        "backend/app/api/v1/endpoints/profile.py"
    ).read_text(encoding="utf-8")

    mobile_api_source = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(encoding="utf-8")

    assert "generate_avatar_signed_url" not in storage_source
    assert "AVATAR_SIGNED_URL_EXPIRY_SECONDS" not in storage_source
    assert "create_signed_url(" not in storage_source
    assert "def download_avatar(" in storage_source

    assert "def download_profile_avatar_content(" in profile_source
    assert '"/avatar/content"' in profile_source
    assert "download_avatar(" in profile_source
    assert "private, no-store, max-age=0" in profile_source
    assert "no-referrer" in profile_source
    assert "nosniff" in profile_source

    assert "materializeBrokeredAvatar(" in mobile_api_source
    assert "FileSystem.downloadAsync(" in mobile_api_source
    assert (
        "Authorization:"
        in mobile_api_source
    )
    assert (
        "'Bearer ' + token"
        in mobile_api_source
    )
    assert (
        "internmatch-avatar-"
        in mobile_api_source
    )
    assert (
        "if (/supabase\\.co/i.test(avatarValue))"
        in mobile_api_source
    )


def test_avatar_profile_response_exposes_no_storage_path():
    from pathlib import Path

    profile_source = Path(
        "backend/app/api/v1/endpoints/profile.py"
    ).read_text(encoding="utf-8")

    assert (
        "/api/v1/profile/avatar/content"
        in profile_source
    )

    assert (
        "avatar_url = generate_avatar_signed_url"
        not in profile_source
    )



def test_all_employer_headline_surfaces_fail_closed():
    import ast
    from pathlib import Path

    application_source = Path(
        "backend/app/schemas/application.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "headline=profile.headline"
        not in application_source
    )

    employer_services = (
        Path(
            "backend/app/services"
        ).glob("employer*.py")
    )

    raw_reads = []

    for path in employer_services:
        source = path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if (
                isinstance(
                    node,
                    ast.Attribute,
                )
                and node.attr
                == "headline"
            ):
                raw_reads.append(
                    (
                        path.name,
                        node.lineno,
                    )
                )

            if (
                isinstance(
                    node,
                    ast.Call,
                )
                and isinstance(
                    node.func,
                    ast.Name,
                )
                and node.func.id
                == "getattr"
                and len(node.args) >= 2
                and isinstance(
                    node.args[1],
                    ast.Constant,
                )
                and node.args[1].value
                == "headline"
            ):
                raw_reads.append(
                    (
                        path.name,
                        node.lineno,
                    )
                )

    assert raw_reads == []


def test_employer_candidate_password_like_headline_is_not_serialized():
    from datetime import (
        date,
        datetime,
        timezone,
    )
    from types import SimpleNamespace
    from uuid import uuid4

    from app.schemas.application import (
        EmployerApplicantResponse,
    )

    secret = (
        "RealTestPassword!"
        "NeverExpose123"
    )

    application = SimpleNamespace(
        id=uuid4(),
        internship_id=uuid4(),
        status="applied",
        applied_date=date.today(),
        generated_cover_letter=None,
        interview_scheduled_at=None,
        interview_mode=None,
        interview_location=None,
        interview_message=None,
        created_at=datetime.now(
            timezone.utc
        ),
        updated_at=datetime.now(
            timezone.utc
        ),
    )

    profile = SimpleNamespace(
        id=uuid4(),
        full_name="Security Candidate",
        headline=secret,
        preferences={},
    )

    response = (
        EmployerApplicantResponse
        .from_orm_data(
            application=application,
            profile=profile,
            match=None,
            skills=[],
            skill_evidence=[],
            ai_rank=None,
        )
    )

    assert (
        response.candidate.headline
        is None
    )

    assert (
        secret
        not in response.model_dump_json()
    )


def test_private_document_browser_contract_is_generic_and_branded():
    from pathlib import Path

    source = Path(
        "backend/app/main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "private_document_browser_guard"
        in source
    )

    assert (
        '"/document-unavailable"'
        in source
    )

    assert "401" in source
    assert "403" in source
    assert "404" in source

    assert "InternMatch AI" in source
    assert "Document unavailable" in source
    assert "تعذر فتح المستند" in source
    assert "Belge açılamıyor" in source

    assert (
        "private, no-store, max-age=0"
        in source
    )

    assert "no-referrer" in source


def test_employer_application_contract_has_no_auth_secret_fields():
    from pathlib import Path

    source = Path(
        "backend/app/schemas/application.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = {
        "password:",
        "access_token:",
        "refresh_token:",
        "service_role",
    }

    for value in forbidden:
        assert value not in source



def test_headline_write_boundary_rejects_credential_like_data():
    profile_source = Path(
        "backend/app/api/v1/endpoints/profile.py"
    ).read_text(
        encoding="utf-8"
    )

    extraction_source = Path(
        "backend/app/repositories/candidate_profile_write.py"
    ).read_text(
        encoding="utf-8"
    )

    security_source = Path(
        "backend/app/services/profile_text_security.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '@field_validator("headline")'
        in profile_source
    )

    assert (
        "normalize_public_profile_headline("
        in profile_source
    )

    assert (
        "sanitize_extracted_profile_headline("
        in extraction_source
    )

    assert (
        "looks_like_sensitive_credential"
        in security_source
    )

    assert (
        "Headline cannot contain credential-like or secret data."
        in security_source
    )


def test_profile_security_errors_do_not_echo_secret_values():
    source = Path(
        "backend/app/services/profile_text_security.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'f"Headline'
        not in source
    )

    assert (
        "repr(value)"
        not in source
    )



def test_production_auth_public_boundary_remains_env_configured_until_custom_domain_activation():
    from pathlib import Path

    mobile_client = Path(
        "apps/mobile/src/lib/supabase.ts"
    ).read_text(
        encoding="utf-8"
    )

    admin_client = Path(
        "apps/admin/lib/supabase.ts"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "process.env.EXPO_PUBLIC_SUPABASE_URL"
        in mobile_client
    )

    assert (
        "process.env.NEXT_PUBLIC_SUPABASE_URL"
        in admin_client
    )

    assert (
        "https://auth.internmatch.college"
        not in mobile_client
    )

    assert (
        "https://auth.internmatch.college"
        not in admin_client
    )

    assert (
        "INTERNMATCH_PRODUCTION_AUTH_URL"
        not in mobile_client
    )

    assert (
        "INTERNMATCH_PRODUCTION_AUTH_URL"
        not in admin_client
    )

def test_confirmation_callback_supports_owned_domain_token_hash():
    from pathlib import Path

    source = Path(
        "apps/mobile/src/services/auth.ts"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "https://internmatch.college/auth/confirmed"
        in source
    )

    assert (
        "confirmationTokenHash"
        in source
    )

    assert (
        "supabase.auth.verifyOtp"
        in source
    )

    assert (
        "token_hash: confirmationTokenHash"
        in source
    )

    assert "type: 'email'" in source


def test_password_recovery_owned_domain_token_hash_contract():
    from pathlib import Path

    source = Path(
        "apps/mobile/src/services/passwordRecovery.ts"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "https://internmatch.college/auth/reset-password"
        in source
    )

    assert (
        "supabase.auth.verifyOtp"
        in source
    )

    assert (
        "token_hash: tokenHash"
        in source
    )

    assert "type: 'recovery'" in source


def test_auth_env_examples_use_provider_placeholders_until_custom_domain_activation():
    from pathlib import Path

    paths = (
        Path(
            "apps/mobile/.env.example"
        ),
        Path(
            "apps/admin/.env.example"
        ),
    )

    for path in paths:
        source = path.read_text(
            encoding="utf-8"
        ).lower()

        assert (
            "https://auth.internmatch.college"
            not in source
        )

        assert (
            "aoioyabrrdptrubjegkf.supabase.co"
            not in source
        )

        assert "supabase.co" in source

def test_public_profile_storage_metadata_boundary():
    from pathlib import Path

    source = Path(
        "backend/app/api/v1/endpoints/profile.py"
    ).read_text(
        encoding="utf-8"
    )

    request_start = source.index(
        "class StudentProfileCreateUpdate"
    )

    response_start = source.index(
        "class StudentProfileResponse"
    )

    request_contract = source[
        request_start:response_start
    ]

    assert (
        "cv_storage_path: Optional[str]"
        not in request_contract
    )

    assert (
        'Field(None, description="Storage path for CV file")'
        not in request_contract
    )

    assert (
        "_reject_server_owned_storage_metadata"
        in request_contract
    )

    assert (
        "payload.cv_storage_path"
        not in source
    )

    assert "has_cv: bool" in source

    response_contract = source[
        response_start:
        source.index(
            "class AvatarUploadResponse"
        )
    ]

    assert "cv_url" not in response_contract
    assert "cv_storage_path" not in response_contract


def test_processing_job_public_boundary_sanitizes_internal_storage_metadata():
    from pathlib import Path

    source = Path(
        "backend/app/schemas/job.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "_sanitize_public_processing_job_result"
        in source
    )

    assert (
        "            result=model.result,`n"
        "            error=model.error,"
        not in source
    )

    assert (
        "result=_sanitize_public_processing_job_result("
        in source
    )

    assert "cv_storage_path" in source
    assert "extracted_profile" in source


def test_mobile_profile_contract_uses_has_cv_not_storage_metadata():
    from pathlib import Path

    paths = (
        Path(
            "apps/mobile/src/services/api.ts"
        ),
        Path(
            "apps/mobile/src/screens/CVUploadScreen.js"
        ),
        Path(
            "apps/mobile/src/screens/HomeScreen.js"
        ),
        Path(
            "apps/mobile/src/screens/MatchupsScreen.js"
        ),
        Path(
            "apps/mobile/src/utils/profileCompleteness.js"
        ),
    )

    combined = "\n".join(
        path.read_text(
            encoding="utf-8"
        )
        for path in paths
    )

    assert "has_cv" in combined
    assert "cv_storage_path" not in combined
    assert "cv_url" not in combined



def test_admin_cv_broker_has_no_provider_or_secret_url_contract():
    endpoint_source = Path(
        "backend/app/api/v1/endpoints/"
        "admin_internships.py"
    ).read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        endpoint_source
    )

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name
        == (
            "download_admin_internship_"
            "applicant_cv_content"
        )
    ]

    assert len(matches) == 1

    node = matches[0]
    assert node.end_lineno is not None

    start = node.lineno

    if node.decorator_list:
        start = min(
            [start]
            + [
                decorator.lineno
                for decorator
                in node.decorator_list
            ]
        )

    endpoint_lines = (
        endpoint_source.splitlines()
    )

    block = "\n".join(
        endpoint_lines[
            start - 1:
            node.end_lineno
        ]
    )

    assert (
        "Depends("
        in block
    )
    assert (
        "require_admin_user"
        in block
    )
    assert (
        "_get_admin_managed_listing("
        in block
    )
    assert (
        "get_applicant_detail_for_admin("
        in block
    )
    assert (
        'application.status == "saved"'
        in block
    )

    assert (
        "download_candidate_cv("
        in block
    )
    assert "Response(" in block

    assert (
        "create_signed_url"
        not in block
    )
    assert (
        "signed_url"
        not in block
    )
    assert (
        "cv_url"
        not in block
    )
    assert (
        "supabase.co"
        not in block
    )

    assert (
        '"private, no-store, max-age=0"'
        in block
    )
    assert (
        '"no-referrer"'
        in block
    )
    assert (
        '"nosniff"'
        in block
    )


def test_admin_cv_browser_uses_ephemeral_authenticated_blob_only():
    admin_api = Path(
        "apps/admin/lib/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    page = Path(
        "apps/admin/app/listings/[id]/"
        "applicants/page.tsx"
    ).read_text(
        encoding="utf-8"
    )

    helper_start = admin_api.index(
        (
            "export async function "
            "downloadAdminInternshipApplicantCV("
        )
    )

    helper_end = admin_api.index(
        (
            "export async function "
            "updateAdminInternshipApplicantStatus("
        ),
        helper_start,
    )

    helper = admin_api[
        helper_start:
        helper_end
    ]

    assert (
        "Authorization:"
        in helper
    )
    assert (
        "'Bearer ' + token"
        in helper
    )

    assert (
        "cache: 'no-store'"
        in helper
    )
    assert (
        "credentials: 'omit'"
        in helper
    )
    assert (
        "redirect: 'error'"
        in helper
    )

    assert (
        "create_signed_url"
        not in helper
    )
    assert (
        "signed_url"
        not in helper
    )
    assert (
        "cv_url"
        not in helper
    )

    assert (
        "downloadAdminInternshipApplicantCV("
        in page
    )
    assert (
        "URL.createObjectURL(blob)"
        in page
    )
    assert (
        "URL.revokeObjectURL("
        in page
    )
    assert (
        "window.open("
        in page
    )

    assert (
        "cv_storage_path"
        not in page
    )
    assert (
        "signed_url"
        not in page
    )
    assert (
        "cv_url"
        not in page
    )

    # Never print session credentials or document
    # bytes into browser logs.
    assert (
        "console.log(token"
        not in admin_api
    )
    assert (
        "console.log(blob"
        not in page
    )


def test_private_document_browser_guard_covers_admin_candidate_cv():
    source = Path(
        "backend/app/main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"/api/v1/admin/internships/"'
        in source
    )

    assert (
        '"/cv/content"'
        in source
    )

    assert (
        '"/document-unavailable"'
        in source
    )
