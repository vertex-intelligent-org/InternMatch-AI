import { getSupabaseClient } from './supabase';
import type {
  AdminApprovalPayload,
  AdminRejectionPayload,
  AdminSuspensionPayload,
  EmployerOrganization,
  VerificationStatus,
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
