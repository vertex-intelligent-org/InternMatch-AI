import Constants from 'expo-constants';
import { supabase } from '../lib/supabase';
import { normalizeLocale, DEFAULT_LOCALE } from '../localization/i18n';

function resolveExpoDevelopmentHost(): string | null {
  const hostUri = Constants.expoConfig?.hostUri?.trim();

  if (!hostUri) {
    return null;
  }

  try {
    const normalizedHostUri = hostUri.includes('://')
      ? hostUri
      : `http://${hostUri}`;

    return new URL(normalizedHostUri).hostname || null;
  } catch {
    return null;
  }
}

function resolveApiBaseUrl(): string {
  const configuredApiBaseUrl = (
    process.env.EXPO_PUBLIC_API_URL ?? ''
  ).replace(/\/+$/, '');

  if (__DEV__) {
    const developmentHost = resolveExpoDevelopmentHost();

    if (developmentHost) {
      return `http://${developmentHost}:8000/api/v1`;
    }
  }

  return configuredApiBaseUrl;
}

const apiBaseUrl = resolveApiBaseUrl();

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type ApiRequestOptions = RequestInit & {
  authenticated?: boolean;
};

async function getAccessToken(): Promise<string> {
  const { data, error } = await supabase.auth.getSession();

  if (error) {
    throw new ApiError(error.message, 401, 'SESSION_ERROR');
  }

  const token = data.session?.access_token;

  if (!token) {
    throw new ApiError('No active authenticated session.', 401, 'UNAUTHENTICATED');
  }

  return token;
}

type JsonRecord = Record<string, unknown>;

function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function extractApiError(payload: unknown, fallback: string) {
  const root = isJsonRecord(payload) ? payload : {};
  const detail = root.detail;
  const detailRecord = isJsonRecord(detail) ? detail : null;

  const rawError =
    detailRecord?.error ??
    root.error;

  const error = isJsonRecord(rawError) ? rawError : null;

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

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  if (!apiBaseUrl) {
    throw new ApiError('EXPO_PUBLIC_API_URL is not configured.', 0, 'API_NOT_CONFIGURED');
  }

  const headers = new Headers(options.headers ?? {});

  if (options.authenticated !== false) {
    const token = await getAccessToken();
    headers.set('Authorization', 'Bearer ' + token);
  }

  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const normalizedPath = path.startsWith('/') ? path : '/' + path;
  const url = apiBaseUrl + normalizedPath;

  let response: Response;

  try {
    if (path === '/profile/cv') {
      console.info(
        `[CV_UPLOAD_DEBUG] request-start url=${url} formData=${options.body instanceof FormData}`
      );
    }

    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network request failed.';

    if (path === '/profile/cv') {
      console.info(
        `[CV_UPLOAD_DEBUG] request-failed error=${error instanceof Error ? error.name : 'unknown'} message=${message}`
      );
    }
    throw new ApiError(message, 0, 'NETWORK_ERROR');
  }

  const contentType = response.headers.get('content-type') ?? '';
  const hasNoContent = response.status === 204 || response.status === 205;
  const payload = hasNoContent
    ? null
    : contentType.includes('application/json')
      ? await response.json()
      : await response.text();

  if (!response.ok) {
    const parsed = extractApiError(
      payload,
      'Request failed with status ' + response.status + '.'
    );

    throw new ApiError(parsed.message, response.status, parsed.code, parsed.details);
  }

  return payload as T;
}

export type AuthSyncResponse = {
  user_id: string;
  email: string | null;
  has_profile: boolean;
};

export async function syncAuthenticatedUser(): Promise<AuthSyncResponse> {
  return apiRequest<AuthSyncResponse>('/auth/sync', {
    method: 'POST',
  });
}

export type EducationEntry = {
  institution: string;
  degree: string;
  start_year: number | null;
  end_year: number | null;
};

export type ExperienceEntry = {
  company: string;
  role: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
};

export type ProjectEntry = {
  title: string;
  tech_stack: string[];
  description: string | null;
};

export type StudentProfileResponse = {
  id: string;
  user_id: string;
  full_name: string;
  headline: string | null;
  skills: string[];
  education: EducationEntry[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  preferences: Record<string, unknown>;
  cv_url: string | null;
  avatar_url?: string | null;
};

export type UpsertProfilePayload = {
  full_name: string;
  headline?: string | null;
  preferences?: Record<string, unknown>;
  skills?: string[];
};

export async function getProfile(): Promise<StudentProfileResponse> {
  return apiRequest<StudentProfileResponse>('/profile', {
    method: 'GET',
  });
}

export async function upsertProfile(
  payload: UpsertProfilePayload
): Promise<StudentProfileResponse> {
  return apiRequest<StudentProfileResponse>('/profile', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

type ReactNativeFormDataFile = {
  uri: string;
  name: string;
  type: string;
};

/**
 * React Native's native FormData implementation accepts URI-backed file
 * descriptors, while the DOM TypeScript declaration only models string/Blob.
 *
 * Keep the compatibility boundary isolated here rather than spreading unsafe
 * casts or TypeScript suppressions across upload call sites.
 */
function appendReactNativeFile(
  formData: FormData,
  fieldName: string,
  file: ReactNativeFormDataFile
): void {
  const nativeAppend = Reflect.get(formData, 'append');

  if (typeof nativeAppend !== 'function') {
    throw new Error('FormData.append is unavailable.');
  }

  nativeAppend.call(formData, fieldName, file);
}

export type AvatarUploadResponse = {
  avatar_url: string;
  message: string;
};

export type AvatarDeleteResponse = {
  avatar_url: null;
  message: string;
};

export async function uploadAvatar(file: {
  uri: string;
  name?: string;
  type?: string;
}): Promise<AvatarUploadResponse> {
  const formData = new FormData();
  appendReactNativeFile(formData, 'file', {
    uri: file.uri,
    name: file.name || 'avatar.jpg',
    type: file.type || 'image/jpeg',
  });

  return apiRequest<AvatarUploadResponse>('/profile/avatar', {
    method: 'POST',
    body: formData,
  });
}

export async function deleteAvatar(): Promise<AvatarDeleteResponse> {
  return apiRequest<AvatarDeleteResponse>('/profile/avatar', {
    method: 'DELETE',
  });
}

export type CVProcessingResponse = {
  job_id: string;
  status: 'queued';
  message: string;
  estimated_seconds: number;
};

export type ProcessingJobResponse = {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress_percent: number;
  result: Record<string, unknown> | null;
  error: string | null;
  updated_at: string;
};

export async function uploadCV(file: {
  uri: string;
  name: string;
  type?: string;
}): Promise<CVProcessingResponse> {
  const formData = new FormData();
  appendReactNativeFile(formData, 'file', {
    uri: file.uri,
    name: file.name,
    type: file.type || 'application/pdf',
  });

  return apiRequest<CVProcessingResponse>('/profile/cv', {
    method: 'POST',
    body: formData,
  });
}

export async function getProcessingJob(
  jobId: string
): Promise<ProcessingJobResponse> {
  return apiRequest<ProcessingJobResponse>(`/jobs/${encodeURIComponent(jobId)}`, {
    method: 'GET',
  });
}

export type CVConfirmReplacementResponse = {
  status: 'completed';
  profile_id: string;
  message: string;
};

export async function confirmCVReplacement(
  jobId: string
): Promise<CVConfirmReplacementResponse> {
  return apiRequest<CVConfirmReplacementResponse>('/profile/cv/confirm', {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId }),
  });
}

export type CVCancelResponse = {
  job_id: string;
  status: 'cancelled';
  message: string;
};

export async function cancelCVAnalysis(
  jobId: string
): Promise<CVCancelResponse> {
  return apiRequest<CVCancelResponse>(
    `/profile/cv/${encodeURIComponent(jobId)}/cancel`,
    {
      method: 'POST',
    }
  );
}

export type InternshipSummary = {
  id: string;
  title: string;
  company: string;
  location: string;
  work_type: string;
  required_skills: string[];
  preferred_skills: string[];
  is_active?: boolean;
  posted_at: string;
};

export type InternshipListResponse = {
  items: InternshipSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type InternshipDetail = {
  id: string;
  title: string;
  company: string;
  location: string;
  work_type: string;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  languages: string[];
  min_education: string | null;
  is_active?: boolean;
  posted_at: string;
};

export type GetInternshipsParams = {
  work_type?: string;
  location?: string;
  skill?: string;
  limit?: number;
  offset?: number;
};

export async function getInternships(
  params: GetInternshipsParams = {}
): Promise<InternshipListResponse> {
  const queryParts: string[] = [];

  if (params.work_type && params.work_type.trim()) {
    queryParts.push(`work_type=${encodeURIComponent(params.work_type.trim())}`);
  }
  if (params.location && params.location.trim()) {
    queryParts.push(`location=${encodeURIComponent(params.location.trim())}`);
  }
  if (params.skill && params.skill.trim()) {
    queryParts.push(`skill=${encodeURIComponent(params.skill.trim())}`);
  }
  if (typeof params.limit === 'number' && params.limit > 0) {
    queryParts.push(`limit=${encodeURIComponent(params.limit.toString())}`);
  }
  if (typeof params.offset === 'number' && params.offset >= 0) {
    queryParts.push(`offset=${encodeURIComponent(params.offset.toString())}`);
  }

  const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

  return apiRequest<InternshipListResponse>(`/internships${queryString}`, {
    method: 'GET',
    authenticated: false,
  });
}

export async function getInternshipDetail(
  id: string,
  locale?: string
): Promise<InternshipDetail> {
  const normalizedLocale = normalizeLocale(locale) || DEFAULT_LOCALE;
  return apiRequest<InternshipDetail>(
    `/internships/${encodeURIComponent(id)}?locale=${encodeURIComponent(normalizedLocale)}`,
    {
      method: 'GET',
      authenticated: false,
    }
  );
}

export type SavedInternshipItem = {
  id: string;
  internship_id: string;
  saved_at: string;
  internship: InternshipSummary;
};

export type SavedInternshipListResponse = {
  items: SavedInternshipItem[];
  total: number;
  limit: number;
  offset: number;
};

export type SaveInternshipResponse = {
  id: string;
  internship_id: string;
  saved_at: string;
  is_saved: boolean;
  message: string;
};

export type UnsaveInternshipResponse = {
  internship_id: string;
  is_saved: boolean;
  message: string;
};

export type GetSavedInternshipsParams = {
  limit?: number;
  offset?: number;
};

export async function getSavedInternships(
  params: GetSavedInternshipsParams = {}
): Promise<SavedInternshipListResponse> {
  const queryParts: string[] = [];

  if (typeof params.limit === 'number' && params.limit > 0) {
    queryParts.push(`limit=${encodeURIComponent(params.limit.toString())}`);
  }
  if (typeof params.offset === 'number' && params.offset >= 0) {
    queryParts.push(`offset=${encodeURIComponent(params.offset.toString())}`);
  }

  const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

  return apiRequest<SavedInternshipListResponse>(`/saved-internships${queryString}`, {
    method: 'GET',
  });
}

export async function saveInternship(
  internshipId: string
): Promise<SaveInternshipResponse> {
  return apiRequest<SaveInternshipResponse>(
    `/saved-internships/${encodeURIComponent(internshipId)}`,
    {
      method: 'POST',
    }
  );
}

export async function unsaveInternship(
  internshipId: string
): Promise<UnsaveInternshipResponse> {
  return apiRequest<UnsaveInternshipResponse>(
    `/saved-internships/${encodeURIComponent(internshipId)}`,
    {
      method: 'DELETE',
    }
  );
}

export type InternshipMatchSummary = {
  id: string;
  title: string;
  company: string;
  location: string;
};

export type MatchItem = {
  match_id: string;
  internship: InternshipMatchSummary;
  overall_score: number;
  skill_score: number;
  vector_score: number;
  created_at: string;
};

export type MatchListResponse = {
  matches: MatchItem[];
};

export type MatchCalculationAcceptedResponse = {
  job_id: string;
  status: 'queued';
  message: string;
};

export type SkillGapAnalysis = {
  summary: string;
  recommendations: string[];
};

export type MatchExplanationResponse = {
  match_id: string;
  overall_score: number;
  why_you_match: string;
  matching_skills: string[];
  missing_skills: string[];
  skill_gap_analysis: SkillGapAnalysis;
};

export async function getMatches(): Promise<MatchListResponse> {
  return apiRequest<MatchListResponse>('/matches', {
    method: 'GET',
  });
}

export async function calculateMatches(): Promise<MatchCalculationAcceptedResponse> {
  return apiRequest<MatchCalculationAcceptedResponse>('/matches/calculate', {
    method: 'POST',
  });
}

export async function getMatchExplanation(
  matchId: string,
  contentLocale?: string
): Promise<MatchExplanationResponse> {
  const normalizedLocale = normalizeLocale(contentLocale) || DEFAULT_LOCALE;
  return apiRequest<MatchExplanationResponse>(
    `/matches/${encodeURIComponent(matchId)}/explanation?content_locale=${encodeURIComponent(normalizedLocale)}`,
    {
      method: 'GET',
    }
  );
}

export type ApplicationStatus =
  | 'saved'
  | 'applied'
  | 'interviewing'
  | 'rejected'
  | 'accepted';

export type ApplicationTrackerItem = {
  id: string;
  internship_id: string | null;
  company_name: string | null;
  job_title: string | null;
  status: ApplicationStatus;
  generated_cover_letter: string | null;
  applied_date: string | null;
  notes: string | null;
};

export type ApplicationStatusEvent = {
  status: ApplicationStatus;
  occurred_at: string;
};

export type ApplicationDetailResponse = {
  id: string;
  internship_id: string | null;
  company_name: string | null;
  job_title: string | null;
  status: ApplicationStatus;
  generated_cover_letter: string | null;
  applied_date: string | null;
  notes: string | null;
  interview_scheduled_at: string | null;
  interview_mode: 'online' | 'onsite' | null;
  interview_location: string | null;
  interview_message: string | null;
  created_at: string;
  updated_at: string;
  timeline: ApplicationStatusEvent[];
};

export type ApplicationListResponse = {
  applications: ApplicationTrackerItem[];
};

export type InterviewPrepResponse = {
  application_id: string;
  interview_scheduled_at: string;
  preparation_summary: string;
  likely_questions: string[];
  focus_areas: string[];
  strengths_to_highlight: string[];
  questions_to_ask: string[];
};

export type ApplicationGenerateAcceptedResponse = {
  job_id: string;
  status: 'queued';
  message: string;
};

export type GenerateApplicationParams = {
  match_id: string;
  tone: string;
  content_locale?: 'en' | 'tr' | 'ar';
};

export type UpdateApplicationStatusPayload = {
  status: ApplicationStatus;
  notes?: string | null;
};

export async function getApplications(): Promise<ApplicationListResponse> {
  return apiRequest<ApplicationListResponse>('/applications', {
    method: 'GET',
  });
}

export async function getApplicationDetail(
  applicationId: string
): Promise<ApplicationDetailResponse> {
  return apiRequest<ApplicationDetailResponse>(
    `/applications/${encodeURIComponent(applicationId)}`,
    {
      method: 'GET',
    }
  );
}


export async function generateInterviewPrep(
  applicationId: string,
  contentLocale?: string
): Promise<InterviewPrepResponse> {
  const normalizedLocale =
    normalizeLocale(contentLocale) || DEFAULT_LOCALE;

  return apiRequest<InterviewPrepResponse>(
    `/applications/${encodeURIComponent(applicationId)}/interview-prep?content_locale=${encodeURIComponent(normalizedLocale)}`,
    {
      method: 'POST',
    }
  );
}

export async function generateApplication(
  payload: GenerateApplicationParams
): Promise<ApplicationGenerateAcceptedResponse> {
  return apiRequest<ApplicationGenerateAcceptedResponse>('/applications/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateApplicationStatus(
  applicationId: string,
  payload: UpdateApplicationStatusPayload
): Promise<ApplicationTrackerItem> {
  return apiRequest<ApplicationTrackerItem>(
    `/applications/${encodeURIComponent(applicationId)}/status`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export type EmployerCreateInternshipPayload = {
  title: string;
  company: string;
  location: string;
  work_type: 'remote' | 'onsite' | 'hybrid';
  description: string;
  required_skills?: string[];
  preferred_skills?: string[];
  language?: string;
  education_requirements?: string | null;
  experience_requirements?: string | null;
};

export type EmployerOpportunityListResponse = {
  items: InternshipSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type EmployerApplicantCandidate = {
  student_id: string;
  full_name: string;
  headline: string | null;
  department: string | null;
  skills: string[];
};

export type EmployerSkillEvidence = {
  name: string;
  cv_evidenced: boolean;
  self_declared: boolean;
  cv_provenance_known: boolean;
};

export type EmployerApplicantItem = {
  application_id: string;
  internship_id: string;
  status: ApplicationStatus;
  applied_date: string | null;
  generated_cover_letter: string | null;
  match_score: number | null;
  skill_score: number | null;
  vector_score: number | null;
  attribute_score: number | null;
  ai_rank: number | null;
  matching_skills: string[];
  missing_skills: string[];
  skill_evidence: EmployerSkillEvidence[];
  interview_scheduled_at: string | null;
  interview_mode: 'online' | 'onsite' | null;
  interview_location: string | null;
  interview_message: string | null;
  created_at: string;
  updated_at: string;
  candidate: EmployerApplicantCandidate;
};

export type EmployerApplicantListResponse = {
  items: EmployerApplicantItem[];
  total: number;
  internship_id: string;
};

export async function createEmployerInternship(
  payload: EmployerCreateInternshipPayload
): Promise<InternshipDetail> {
  return apiRequest<InternshipDetail>('/internships', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateEmployerInternship(
  id: string,
  payload: EmployerCreateInternshipPayload
): Promise<InternshipDetail> {
  return apiRequest<InternshipDetail>(
    `/internships/${encodeURIComponent(id)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export async function getEmployerInternships(
  params: {
    limit?: number;
    offset?: number;
  } = {}
): Promise<EmployerOpportunityListResponse> {
  const queryParts: string[] = [];

  if (typeof params.limit === 'number' && params.limit > 0) {
    queryParts.push(`limit=${encodeURIComponent(params.limit.toString())}`);
  }
  if (typeof params.offset === 'number' && params.offset >= 0) {
    queryParts.push(`offset=${encodeURIComponent(params.offset.toString())}`);
  }

  const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

  return apiRequest<EmployerOpportunityListResponse>(`/internships/mine${queryString}`, {
    method: 'GET',
  });
}

export async function getEmployerApplicants(
  internshipId: string
): Promise<EmployerApplicantListResponse> {
  return apiRequest<EmployerApplicantListResponse>(
    `/internships/${encodeURIComponent(internshipId)}/applicants`,
    {
      method: 'GET',
    }
  );
}

export type EmployerCVAccessResponse = {
  cv_url: string;
  expires_in: number;
  file_type: 'pdf' | 'docx';
};

export async function getEmployerApplicantCV(
  internshipId: string,
  applicationId: string
): Promise<EmployerCVAccessResponse> {
  return apiRequest<EmployerCVAccessResponse>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}/cv`
  );
}

export async function getEmployerApplicantDetail(
  internshipId: string,
  applicationId: string
): Promise<EmployerApplicantItem> {
  return apiRequest<EmployerApplicantItem>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}`,
    {
      method: 'GET',
    }
  );
}

export async function closeEmployerOpportunity(
  id: string
): Promise<InternshipDetail> {
  return apiRequest<InternshipDetail>(
    `/internships/${encodeURIComponent(id)}/close`,
    {
      method: 'POST',
    }
  );
}

export type EmployerInterviewSchedulePayload = {
  scheduled_at: string;
  mode: 'online' | 'onsite';
  location: string;
  message?: string | null;
};

export async function scheduleEmployerApplicantInterview(
  internshipId: string,
  applicationId: string,
  payload: EmployerInterviewSchedulePayload
): Promise<EmployerApplicantItem> {
  return apiRequest<EmployerApplicantItem>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}/interview`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function updateEmployerApplicantStatus(
  internshipId: string,
  applicationId: string,
  payload: { status: ApplicationStatus; notes?: string }
): Promise<EmployerApplicantItem> {
  return apiRequest<EmployerApplicantItem>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}/status`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export async function submitApplication(
  applicationId: string,
  payload?: { cover_letter?: string; notes?: string }
): Promise<ApplicationDetailResponse> {
  return apiRequest<ApplicationDetailResponse>(
    `/applications/${encodeURIComponent(applicationId)}/submit`,
    {
      method: 'POST',
      body: payload ? JSON.stringify(payload) : JSON.stringify({}),
    }
  );
}

export async function discardApplicationDraft(
  applicationId: string
): Promise<void> {
  await apiRequest<void>(
    `/applications/${encodeURIComponent(applicationId)}`,
    {
      method: 'DELETE',
    }
  );
}
// -----------------------------------------------------------------------------
// Backend-authoritative Student subscription + AI usage state
// -----------------------------------------------------------------------------

export type BackendSubscriptionResponse = {
  plan: 'free' | 'pro_student' | 'employer_pro';
  entitlement_id: string;
  is_active: boolean;
  status: string;
  will_renew: boolean;
  expires_at: string | null;
  product_id: string | null;
  environment: string | null;
  store: string | null;
  last_event_type: string | null;
};

export type AIQuotaFeatureResponse = {
  feature_key:
    | 'cv_analysis'
    | 'match_explanation'
    | 'application_support'
    | 'interview_prep';
  display_name: string;
  limit: number;
  used: number;
  remaining: number;
  reset_policy: string;
  period_started_at: string;
  reset_at: string;
};

export type AIUsageResponse = {
  plan: 'free' | 'pro_student';
  features: AIQuotaFeatureResponse[];
};

export type SubscriptionReconciliationResponse = {
  outcome: string;
  subscription: BackendSubscriptionResponse;
};

/**
 * Product authorization source of truth.
 * RevenueCat remains the billing/purchase provider, while access decisions
 * are read from the authenticated backend.
 */
export async function getMySubscription(): Promise<BackendSubscriptionResponse> {
  return apiRequest<BackendSubscriptionResponse>('/me/subscription');
}

/**
 * Backend-controlled user-facing AI quota snapshot.
 */
export async function getMyAIUsage(): Promise<AIUsageResponse> {
  return apiRequest<AIUsageResponse>('/me/ai-usage');
}

/**
 * Refresh backend subscription state from RevenueCat after purchase/restore.
 */
export async function reconcileMySubscription(): Promise<SubscriptionReconciliationResponse> {
  return apiRequest<SubscriptionReconciliationResponse>(
    '/me/subscription/reconcile',
    {
      method: 'POST',
    }
  );
}
