import { getSupabaseClient } from './supabase';
import type {
  AdminApprovalPayload,
  AdminRejectionPayload,
  AdminSuspensionPayload,
  AdminInternshipCreatePayload,
  AdminInternshipDetail,
  AdminInternshipListResponse,
  PublicationStatus,
  EmployerOrganization,
  VerificationStatus,
  ComplianceClaimStatus,
  EmployerComplianceClaim,
  ComplianceAdminApprovalPayload,
  ComplianceAdminRejectionPayload,
  ComplianceAdminRevocationPayload,
  AdminUserRole,
  AdminUserListResponse,
  AdminUserDetail,
  AdminApplicantItem,
  AdminApplicantListResponse,
  AdminApplicantStatusPayload,
  AdminInterviewSchedulePayload,
  AdminPromoCampaign,
  AdminPromoCampaignCreatePayload,
  PromoAudience,
} from './types';

type JsonRecord = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(
    message: string,
    status: number,
    code?: string,
    details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isJsonRecord(value: unknown): value is JsonRecord {
  return (
    typeof value === 'object'
    && value !== null
    && !Array.isArray(value)
  );
}

function extractApiError(
  payload: unknown,
  fallback: string
): {
  message: string;
  code?: string;
  details?: unknown;
} {
  const root = isJsonRecord(payload) ? payload : {};
  const detail = root.detail;
  const detailRecord = isJsonRecord(detail)
    ? detail
    : null;

  const rawError =
    detailRecord?.error
    ?? root.error;

  const error = isJsonRecord(rawError)
    ? rawError
    : null;

  const message =
    typeof error?.message === 'string'
      ? error.message
      : typeof detail === 'string'
        ? detail
        : fallback;

  const code =
    typeof error?.code === 'string'
      ? error.code
      : undefined;

  return {
    message,
    code,
    details: error?.details,
  };
}

function resolveApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL ?? ''
  )
    .trim()
    .replace(/\/+$/, '');
}

async function getAccessToken(): Promise<string> {
  const supabase = getSupabaseClient();

  const {
    data,
    error,
  } = await supabase.auth.getSession();

  if (error) {
    throw new ApiError(
      error.message,
      401,
      'SESSION_ERROR'
    );
  }

  const token = data.session?.access_token;

  if (!token) {
    throw new ApiError(
      'No active authenticated session.',
      401,
      'UNAUTHENTICATED'
    );
  }

  return token;
}

async function adminApiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const apiBaseUrl = resolveApiBaseUrl();

  if (!apiBaseUrl) {
    throw new ApiError(
      'NEXT_PUBLIC_API_URL is not configured.',
      0,
      'API_NOT_CONFIGURED'
    );
  }

  const token = await getAccessToken();
  const headers = new Headers(options.headers ?? {});

  headers.set(
    'Authorization',
    `Bearer ${token}`
  );

  headers.set(
    'Accept',
    'application/json'
  );

  if (
    options.body
    && !headers.has('Content-Type')
  ) {
    headers.set(
      'Content-Type',
      'application/json'
    );
  }

  const normalizedPath = path.startsWith('/')
    ? path
    : `/${path}`;

  let response: Response;

  try {
    response = await fetch(
      `${apiBaseUrl}${normalizedPath}`,
      {
        ...options,
        headers,
        cache: 'no-store',
      }
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : 'Network request failed.';

    throw new ApiError(
      message,
      0,
      'NETWORK_ERROR'
    );
  }

  const contentType =
    response.headers.get('content-type')
    ?? '';

  const hasNoContent =
    response.status === 204
    || response.status === 205;

  const payload: unknown = hasNoContent
    ? null
    : contentType.includes(
        'application/json'
      )
      ? await response.json()
      : await response.text();

  if (!response.ok) {
    const parsed = extractApiError(
      payload,
      `Request failed with status ${response.status}.`
    );

    throw new ApiError(
      parsed.message,
      response.status,
      parsed.code,
      parsed.details
    );
  }

  return payload as T;
}

export async function listOrganizationsForReview(
  verificationStatus: VerificationStatus = 'pending'
): Promise<EmployerOrganization[]> {
  return adminApiRequest<EmployerOrganization[]>(
    (
      '/admin/employer-organizations'
      + `?status=${encodeURIComponent(verificationStatus)}`
    ),
    {
      method: 'GET',
    }
  );
}

export async function getOrganizationForReview(
  organizationId: string
): Promise<EmployerOrganization> {
  return adminApiRequest<EmployerOrganization>(
    (
      '/admin/employer-organizations/'
      + encodeURIComponent(organizationId)
    ),
    {
      method: 'GET',
    }
  );
}

export async function approveOrganization(
  organizationId: string,
  payload: AdminApprovalPayload
): Promise<EmployerOrganization> {
  return adminApiRequest<EmployerOrganization>(
    (
      '/admin/employer-organizations/'
      + encodeURIComponent(organizationId)
      + '/approve'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function rejectOrganization(
  organizationId: string,
  payload: AdminRejectionPayload
): Promise<EmployerOrganization> {
  return adminApiRequest<EmployerOrganization>(
    (
      '/admin/employer-organizations/'
      + encodeURIComponent(organizationId)
      + '/reject'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function suspendOrganization(
  organizationId: string,
  payload: AdminSuspensionPayload
): Promise<EmployerOrganization> {
  return adminApiRequest<EmployerOrganization>(
    (
      '/admin/employer-organizations/'
      + encodeURIComponent(organizationId)
      + '/suspend'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}
export async function createAdminInternship(
  payload: AdminInternshipCreatePayload
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    '/admin/internships',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function listAdminInternships(
  publicationStatus?: PublicationStatus,
  limit = 20,
  offset = 0
): Promise<AdminInternshipListResponse> {
  const params = new URLSearchParams();

  if (publicationStatus) {
    params.set(
      'publication_status',
      publicationStatus
    );
  }

  params.set('limit', String(limit));
  params.set('offset', String(offset));

  return adminApiRequest<AdminInternshipListResponse>(
    '/admin/internships?' + params.toString(),
    {
      method: 'GET',
    }
  );
}

export async function getAdminInternship(
  internshipId: string
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
    ),
    {
      method: 'GET',
    }
  );
}

export async function closeAdminInternship(
  internshipId: string
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/close'
    ),
    {
      method: 'POST',
    }
  );
}

export async function reopenAdminInternship(
  internshipId: string
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/reopen'
    ),
    {
      method: 'POST',
    }
  );
}

export async function listComplianceClaimsForReview(
  claimStatus: ComplianceClaimStatus = 'pending'
): Promise<EmployerComplianceClaim[]> {
  return adminApiRequest<EmployerComplianceClaim[]>(
    (
      '/admin/employer-compliance/claims'
      + `?status=${encodeURIComponent(claimStatus)}`
    ),
    {
      method: 'GET',
    }
  );
}

export async function getComplianceClaimForReview(
  claimId: string
): Promise<EmployerComplianceClaim> {
  return adminApiRequest<EmployerComplianceClaim>(
    (
      '/admin/employer-compliance/claims/'
      + encodeURIComponent(claimId)
    ),
    {
      method: 'GET',
    }
  );
}

export async function downloadComplianceEvidence(
  claimId: string,
  evidenceId: string
): Promise<Blob> {
  const apiBaseUrl =
    (process.env.NEXT_PUBLIC_API_URL || '')
      .replace(/\/+$/, '');

  if (!apiBaseUrl) {
    throw new ApiError(
      'NEXT_PUBLIC_API_URL is not configured.',
      0,
      'API_NOT_CONFIGURED'
    );
  }

  const supabase = getSupabaseClient();

  const { data, error } =
    await supabase.auth.getSession();

  if (error) {
    throw new ApiError(
      error.message,
      401,
      'SESSION_ERROR'
    );
  }

  const token =
    data.session?.access_token;

  if (!token) {
    throw new ApiError(
      'No active authenticated session.',
      401,
      'UNAUTHENTICATED'
    );
  }

  const path =
    '/admin/employer-compliance/claims/'
    + encodeURIComponent(claimId)
    + '/evidence/'
    + encodeURIComponent(evidenceId)
    + '/content';

  const url =
    apiBaseUrl + path;

  if (/supabase\.co/i.test(url)) {
    throw new ApiError(
      'Provider URLs are not permitted for compliance evidence.',
      0,
      'PROVIDER_URL_BLOCKED'
    );
  }

  let response: Response;

  try {
    response = await fetch(
      url,
      {
        method: 'GET',
        headers: {
          Authorization: 'Bearer ' + token,
        },
        cache: 'no-store',
      }
    );
  } catch {
    throw new ApiError(
      'Compliance evidence request failed.',
      0,
      'NETWORK_ERROR'
    );
  }

  if (!response.ok) {
    throw new ApiError(
      response.status === 404
        ? 'This document is unavailable or you do not have permission to access it.'
        : 'Compliance evidence could not be opened.',
      response.status,
      'EVIDENCE_ACCESS_DENIED'
    );
  }

  return response.blob();
}


export async function approveComplianceClaim(
  claimId: string,
  payload: ComplianceAdminApprovalPayload
): Promise<EmployerComplianceClaim> {
  return adminApiRequest<EmployerComplianceClaim>(
    (
      '/admin/employer-compliance/claims/'
      + encodeURIComponent(claimId)
      + '/approve'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function rejectComplianceClaim(
  claimId: string,
  payload: ComplianceAdminRejectionPayload
): Promise<EmployerComplianceClaim> {
  return adminApiRequest<EmployerComplianceClaim>(
    (
      '/admin/employer-compliance/claims/'
      + encodeURIComponent(claimId)
      + '/reject'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function revokeComplianceClaim(
  claimId: string,
  payload: ComplianceAdminRevocationPayload
): Promise<EmployerComplianceClaim> {
  return adminApiRequest<EmployerComplianceClaim>(
    (
      '/admin/employer-compliance/claims/'
      + encodeURIComponent(claimId)
      + '/revoke'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export type ListAdminUsersParams = {
  query?: string;
  role?: AdminUserRole;
  offset?: number;
  limit?: number;
};

export async function listAdminUsers(
  params: ListAdminUsersParams = {}
): Promise<AdminUserListResponse> {
  const search = new URLSearchParams();

  if (params.query?.trim()) {
    search.set(
      'query',
      params.query.trim()
    );
  }

  if (params.role) {
    search.set(
      'role',
      params.role
    );
  }

  search.set(
    'offset',
    String(params.offset ?? 0)
  );

  search.set(
    'limit',
    String(params.limit ?? 50)
  );

  return adminApiRequest<AdminUserListResponse>(
    '/admin/users?' + search.toString()
  );
}

export async function getAdminUser(
  userId: string
): Promise<AdminUserDetail> {
  return adminApiRequest<AdminUserDetail>(
    '/admin/users/'
    + encodeURIComponent(userId)
  );
}


export async function approveAdminInternship(
  internshipId: string
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/approve'
    ),
    {
      method: 'POST',
    }
  );
}

export type AdminInternshipChangesRequestPayload = {
  employer_visible_feedback: string;
};

export async function requestChangesAdminInternship(
  internshipId: string,
  payload: AdminInternshipChangesRequestPayload
): Promise<AdminInternshipDetail> {
  return adminApiRequest<AdminInternshipDetail>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/request-changes'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function listAdminInternshipApplicants(
  internshipId: string
): Promise<AdminApplicantListResponse> {
  return adminApiRequest<AdminApplicantListResponse>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/applicants'
    ),
    {
      method: 'GET',
    }
  );
}



export async function downloadAdminInternshipApplicantCV(
  internshipId: string,
  applicationId: string
): Promise<Blob> {
  const apiBaseUrl =
    resolveApiBaseUrl();

  if (!apiBaseUrl) {
    throw new ApiError(
      'NEXT_PUBLIC_API_URL is not configured.',
      0,
      'API_NOT_CONFIGURED'
    );
  }

  const token =
    await getAccessToken();

  const path =
    '/admin/internships/'
    + encodeURIComponent(internshipId)
    + '/applicants/'
    + encodeURIComponent(applicationId)
    + '/cv/content';

  const url =
    apiBaseUrl + path;

  // Never allow the browser client to consume
  // a storage-provider URL directly.
  if (/supabase\.co/i.test(url)) {
    throw new ApiError(
      'Storage-provider CV URLs are not permitted.',
      0,
      'PROVIDER_URL_BLOCKED'
    );
  }

  let response: Response;

  try {
    response = await fetch(
      url,
      {
        method: 'GET',
        headers: {
          Authorization:
            'Bearer ' + token,
          Accept: (
            'application/pdf,'
            + 'application/msword,'
            + 'application/vnd.openxmlformats-'
            + 'officedocument.wordprocessingml.document'
          ),
        },
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
      }
    );
  } catch {
    throw new ApiError(
      'Candidate CV request failed.',
      0,
      'NETWORK_ERROR'
    );
  }

  if (!response.ok) {
    throw new ApiError(
      (
        response.status === 403
        || response.status === 404
      )
        ? (
            'This CV is unavailable or you '
            + 'do not have permission to access it.'
          )
        : (
            'Candidate CV could not be opened.'
          ),
      response.status,
      'CV_ACCESS_DENIED'
    );
  }

  const contentType =
    (
      response.headers
        .get('content-type')
      ?? ''
    )
      .split(';', 1)[0]
      .trim()
      .toLowerCase();

  const allowedContentTypes =
    new Set([
      'application/pdf',
      'application/msword',
      (
        'application/vnd.openxmlformats-'
        + 'officedocument.'
        + 'wordprocessingml.document'
      ),
    ]);

  if (
    !allowedContentTypes.has(
      contentType
    )
  ) {
    throw new ApiError(
      'Candidate CV format is not supported.',
      415,
      'CV_CONTENT_TYPE_INVALID'
    );
  }

  return response.blob();
}


export async function updateAdminInternshipApplicantStatus(
  internshipId: string,
  applicationId: string,
  payload: AdminApplicantStatusPayload
): Promise<AdminApplicantItem> {
  return adminApiRequest<AdminApplicantItem>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/applicants/'
      + encodeURIComponent(applicationId)
      + '/status'
    ),
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export async function scheduleAdminInternshipApplicantInterview(
  internshipId: string,
  applicationId: string,
  payload: AdminInterviewSchedulePayload
): Promise<AdminApplicantItem> {
  return adminApiRequest<AdminApplicantItem>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
      + '/applicants/'
      + encodeURIComponent(applicationId)
      + '/interview'
    ),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteAdminInternship(
  internshipId: string
): Promise<void> {
  await adminApiRequest<void>(
    (
      '/admin/internships/'
      + encodeURIComponent(internshipId)
    ),
    {
      method: 'DELETE',
    }
  );
}


// ---------------------------------------------------------------------
// Private promotional campaign administration.
// ---------------------------------------------------------------------

export async function listAdminPromoCampaigns(
  audience?: PromoAudience
): Promise<AdminPromoCampaign[]> {
  const suffix = audience
    ? (
        "?audience="
        + encodeURIComponent(audience)
      )
    : "";

  return adminApiRequest<
    AdminPromoCampaign[]
  >(
    "/admin/promo-codes" + suffix,
    {
      method: "GET",
    }
  );
}

export async function createAdminPromoCampaign(
  payload: AdminPromoCampaignCreatePayload
): Promise<AdminPromoCampaign> {
  return adminApiRequest<
    AdminPromoCampaign
  >(
    "/admin/promo-codes",
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function publishAdminPromoCampaign(
  campaignId: string
): Promise<AdminPromoCampaign> {
  return adminApiRequest<
    AdminPromoCampaign
  >(
    (
      "/admin/promo-codes/"
      + encodeURIComponent(campaignId)
      + "/publish"
    ),
    {
      method: "POST",
    }
  );
}

export async function retireAdminPromoCampaign(
  campaignId: string
): Promise<AdminPromoCampaign> {
  return adminApiRequest<
    AdminPromoCampaign
  >(
    (
      "/admin/promo-codes/"
      + encodeURIComponent(campaignId)
      + "/retire"
    ),
    {
      method: "POST",
    }
  );
}
