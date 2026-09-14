"""
API v1 Router Aggregator
Includes all sub-routers for version 1 of the REST API.
"""

from app.api.v1.endpoints import (
    admin_internships,
    applications,
    auth,
    health,
    internships,
    jobs,
    matches,
    profile,
    saved_internships,
    subscriptions,
    webhooks,
)
from app.api.v1.endpoints import (
    employer_compliance as employer_compliance_endpoints,
)
from app.api.v1.endpoints import (
    employer_organizations as employer_organizations_endpoints,
)
from fastapi import APIRouter

api_v1_router = APIRouter()

# Register operational health router
api_v1_router.include_router(health.router, tags=["Health Operations"])

# Register authentication router
api_v1_router.include_router(
    auth.router, prefix="/auth", tags=["Authentication Operations"]
)
# Backend-authoritative authenticated subscription state
api_v1_router.include_router(
    subscriptions.router,
    prefix="/me",
    tags=["Subscription Operations"],
)

# External provider webhook ingress
api_v1_router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["Webhook Operations"],
)

# Register protected candidate profile router
api_v1_router.include_router(
    profile.router, prefix="/profile", tags=["Profile Operations"]
)

# Register public internship catalog router
api_v1_router.include_router(
    internships.router, prefix="/internships", tags=["Internship Catalog"]
)

# Register candidate saved internships router
api_v1_router.include_router(
    saved_internships.router,
    prefix="/saved-internships",
    tags=["Saved Internships"],
)

# Register processing job status tracking router
api_v1_router.include_router(
    jobs.router, prefix="/jobs", tags=["Job Tracking"]
)

# Register candidate match engine router
api_v1_router.include_router(
    matches.router, prefix="/matches", tags=["Match Operations"]
)

# Register candidate application operations router
api_v1_router.include_router(
    applications.router,
    prefix="/applications",
    tags=["Application Operations"],
)

# Gate 2 employer organization verification routes
api_v1_router.include_router(
    employer_organizations_endpoints.employer_router,
    prefix="/employer-organization",
    tags=["Employer Organization"],
)

api_v1_router.include_router(
    employer_organizations_endpoints.admin_router,
    prefix="/admin/employer-organizations",
    tags=["Admin Employer Verification"],
)

# Employer compliance claims are a separate trust domain from
# organization identity verification.
api_v1_router.include_router(
    employer_compliance_endpoints.employer_router,
    prefix="/employer-compliance",
    tags=["Employer Compliance"],
)

api_v1_router.include_router(
    employer_compliance_endpoints.admin_router,
    prefix="/admin/employer-compliance",
    tags=["Admin Employer Compliance"],
)

api_v1_router.include_router(
    admin_internships.router,
    prefix="/admin/internships",
    tags=["Admin Internship Listings"],
)
