import Constants from 'expo-constants';
import { supabase } from '../lib/supabase';
import * as FileSystem from 'expo-file-system/legacy';
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

  if (configuredApiBaseUrl) {
    return configuredApiBaseUrl;
  }

  if (__DEV__) {
    const developmentHost = resolveExpoDevelopmentHost();

    if (developmentHost) {
      return `http://${developmentHost}:8000/api/v1`;
    }
  }

  return '';
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

async function rawApiRequest<T>(
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
  has_cv: boolean;
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

export type CompleteSignupPayload = {
  full_name: string;
  department?: string | null;
  account_type: 'intern' | 'employer';
};

export type CompleteSignupResponse = {
  created: boolean;
  user_id: string;
  account_type: 'intern' | 'employer';
};

export async function completeSignup(
  payload: CompleteSignupPayload
): Promise<CompleteSignupResponse> {
  return apiRequest<CompleteSignupResponse>('/auth/complete-signup', {
    method: 'POST',
    body: JSON.stringify(payload),
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

export type AIJobAcceptedResponse = {
  job_id: string;
  status: 'queued';
  message: string;
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
): Promise<AIJobAcceptedResponse> {
  const normalizedLocale = normalizeLocale(contentLocale) || DEFAULT_LOCALE;
  return apiRequest<AIJobAcceptedResponse>(
    `/matches/${encodeURIComponent(matchId)}/explanation?content_locale=${encodeURIComponent(normalizedLocale)}`, {
    method: 'POST',
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
): Promise<AIJobAcceptedResponse> {
  const normalizedLocale =
    normalizeLocale(contentLocale) || DEFAULT_LOCALE;

  return apiRequest<AIJobAcceptedResponse>(
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

export type EmployerVerificationStatus =
  | 'unverified'
  | 'pending'
  | 'verified'
  | 'rejected'
  | 'suspended';

export type EmployerOrganizationType =
  | 'company'
  | 'university_lab'
  | 'research_center';

export type EmployerVerificationMethod =
  | 'standard_company'
  | 'manual_admin';

export type EmployerOrganizationWritePayload = {
  legal_name: string;
  display_name: string;
  website_url: string;
  business_email: string;
  country_code: string;
  registration_number?: string | null;
  tax_number?: string | null;
  representative_name: string;
  representative_role: string;
};

export type EmployerOrganizationResponse = {
  id: string;
  owner_user_id: string;
  legal_name: string;
  display_name: string;
  website_url: string;
  normalized_domain: string;
  business_email: string;
  email_domain_matches_website: boolean;
  country_code: string;
  registration_number: string | null;
  tax_number: string | null;
  representative_name: string;
  representative_role: string;
  organization_type: EmployerOrganizationType;
  verification_method: EmployerVerificationMethod | null;
  verification_status: EmployerVerificationStatus;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason_code: string | null;
  created_at: string;
  updated_at: string;
};

export async function getEmployerOrganization(): Promise<EmployerOrganizationResponse> {
  return apiRequest<EmployerOrganizationResponse>(
    '/employer-organization',
    {
      method: 'GET',
    }
  );
}

export async function createEmployerOrganization(
  payload: EmployerOrganizationWritePayload
): Promise<EmployerOrganizationResponse> {
  return apiRequest<EmployerOrganizationResponse>(
    '/employer-organization',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function updateEmployerOrganization(
  payload: EmployerOrganizationWritePayload
): Promise<EmployerOrganizationResponse> {
  return apiRequest<EmployerOrganizationResponse>(
    '/employer-organization',
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    }
  );
}

export async function submitEmployerOrganizationForReview(): Promise<EmployerOrganizationResponse> {
  return apiRequest<EmployerOrganizationResponse>(
    '/employer-organization/submit',
    {
      method: 'POST',
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


export type EmployerInternshipDescriptionRequest = {
  title: string;
  raw_description: string;
  location?: string | null;
  work_type?: string | null;
  required_skills?: string[];
  preferred_skills?: string[];
  languages?: string[];
  min_education?: string | null;
};

export type EmployerInternshipDescriptionResponse = {
  suggested_description: string;
  responsibilities: string[];
  requirements_summary: string[];
  preferred_qualifications: string[];
  draft_only: true;
  requires_employer_review: true;
  auto_published: false;
};

export async function generateEmployerInternshipDescription(
  payload: EmployerInternshipDescriptionRequest,
  idempotencyKey: string,
  locale?: string
): Promise<EmployerInternshipDescriptionResponse> {
  const contentLocale = normalizeLocale(locale) || DEFAULT_LOCALE;

  return apiRequest<EmployerInternshipDescriptionResponse>(
    `/internships/employer-tools/description-assistant?content_locale=${encodeURIComponent(contentLocale)}`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(payload),
    }
  );
}

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


export type EmployerProductPolicyResponse = {
  plan: 'free' | 'employer_pro';
  is_pro: boolean;
  active_listing_limit: number | null;
  candidate_insight_available: boolean;
  interview_kit_available: boolean;
  shortlist_comparison_available: boolean;
  internship_description_available: boolean;
  pipeline_analytics_available: boolean;
};

export type EmployerPipelineListingCounts = {
  total: number;
  draft: number;
  under_review: number;
  published: number;
  closed: number;
};

export type EmployerPipelineApplicationCounts = {
  total_submitted: number;
  applied: number;
  interviewing: number;
  accepted: number;
  rejected: number;
};

export type EmployerPipelinePercentages = {
  interviewing_share_percent: number | null;
  decision_share_percent: number | null;
  acceptance_share_percent: number | null;
};

export type EmployerPipelineAnalyticsResponse = {
  listing_counts: EmployerPipelineListingCounts;
  application_counts: EmployerPipelineApplicationCounts;
  percentages: EmployerPipelinePercentages;
};

export async function getEmployerProductPolicy(): Promise<EmployerProductPolicyResponse> {
  return apiRequest<EmployerProductPolicyResponse>(
    '/internships/employer-tools/product-policy',
    {
      method: 'GET',
    }
  );
}

export async function getEmployerPipelineAnalytics(): Promise<EmployerPipelineAnalyticsResponse> {
  return apiRequest<EmployerPipelineAnalyticsResponse>(
    '/internships/employer-tools/pipeline-analytics',
    {
      method: 'GET',
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


export type EmployerShortlistComparisonRequest = {
  application_ids: string[];
};

export type EmployerShortlistCandidate = {
  application_id: string;
  match_score: number;
  evidence_highlights: string[];
  gaps_to_validate: string[];
  interview_focus: string[];
  matching_skills: string[];
  missing_skills: string[];
};

export type EmployerShortlistComparisonResponse = {
  internship_id: string;
  comparison_summary: string;
  shared_role_requirements: string[];
  candidates: EmployerShortlistCandidate[];
  ranked: false;
  recommendation_provided: false;
  human_decision_required: true;
};

export async function compareEmployerShortlist(
  internshipId: string,
  applicationIds: string[],
  idempotencyKey: string,
  locale?: string
): Promise<EmployerShortlistComparisonResponse> {
  const contentLocale = normalizeLocale(locale) || DEFAULT_LOCALE;

  return apiRequest<EmployerShortlistComparisonResponse>(
    `/internships/${encodeURIComponent(internshipId)}/shortlist-comparison?content_locale=${encodeURIComponent(contentLocale)}`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({
        application_ids: applicationIds,
      }),
    }
  );
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

export type EmployerCVLocalFile = {
  uri: string;
  mime_type: string;
  file_type: 'pdf' | 'doc' | 'docx' | 'bin';
};

function resolveEmployerCVFileType(
  mimeType: string | null | undefined
): EmployerCVLocalFile['file_type'] {
  const normalized = (mimeType || '')
    .split(';')[0]
    .trim()
    .toLowerCase();

  if (normalized === 'application/pdf') {
    return 'pdf';
  }

  if (normalized === 'application/msword') {
    return 'doc';
  }

  if (
    normalized ===
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  ) {
    return 'docx';
  }

  return 'bin';
}

/**
 * Download an employer-authorized candidate CV through the InternMatch API.
 *
 * Security invariants:
 * - authentication token travels only in the Authorization header
 * - every download hits the server-side application ownership check
 * - no Supabase Storage URL/token is returned to the mobile client
 * - bytes are written only to the app cache as a temporary local file
 */
export async function downloadEmployerApplicantCV(
  internshipId: string,
  applicationId: string
): Promise<EmployerCVLocalFile> {
  if (!apiBaseUrl) {
    throw new ApiError(
      'EXPO_PUBLIC_API_URL is not configured.',
      0,
      'API_NOT_CONFIGURED'
    );
  }

  const token = await getAccessToken();

  const path =
    `/internships/${encodeURIComponent(internshipId)}` +
    `/applicants/${encodeURIComponent(applicationId)}/cv/content`;

  const url = apiBaseUrl + path;

  if (/supabase\.co/i.test(url)) {
    throw new ApiError(
      'Provider URLs are not permitted for candidate document access.',
      0,
      'PROVIDER_URL_BLOCKED'
    );
  }

  const cacheDirectory = FileSystem.cacheDirectory;

  if (!cacheDirectory) {
    throw new ApiError(
      'Temporary file storage is unavailable on this device.',
      0,
      'FILE_CACHE_UNAVAILABLE'
    );
  }

  const safeApplicationId = applicationId.replace(
    /[^a-zA-Z0-9-]/g,
    ''
  );

  const stem =
    `internmatch-cv-${Date.now()}-${safeApplicationId}`;

  const temporaryUri =
    `${cacheDirectory}${stem}.download`;

  let result;

  try {
    result = await FileSystem.downloadAsync(
      url,
      temporaryUri,
      {
        headers: {
          Authorization: 'Bearer ' + token,
        },
      }
    );
  } catch {
    await FileSystem.deleteAsync(
      temporaryUri,
      { idempotent: true }
    ).catch(() => {});

    throw new ApiError(
      'Candidate CV download failed.',
      0,
      'CV_DOWNLOAD_FAILED'
    );
  }

  if (result.status < 200 || result.status >= 300) {
    await FileSystem.deleteAsync(
      result.uri,
      { idempotent: true }
    ).catch(() => {});

    throw new ApiError(
      'Candidate CV download was rejected.',
      result.status,
      'CV_DOWNLOAD_REJECTED'
    );
  }

  const contentTypeHeader = Object.entries(
    result.headers || {}
  ).find(
    ([key]) => key.toLowerCase() === 'content-type'
  )?.[1];

  const mimeType = (
    typeof contentTypeHeader === 'string'
      ? contentTypeHeader
      : 'application/octet-stream'
  )
    .split(';')[0]
    .trim();

  const fileType = resolveEmployerCVFileType(mimeType);

  const finalUri =
    `${cacheDirectory}${stem}.${fileType}`;

  try {
    if (result.uri !== finalUri) {
      await FileSystem.moveAsync({
        from: result.uri,
        to: finalUri,
      });
    }
  } catch {
    await FileSystem.deleteAsync(
      result.uri,
      { idempotent: true }
    ).catch(() => {});

    throw new ApiError(
      'Candidate CV could not be prepared for viewing.',
      0,
      'CV_LOCAL_FILE_FAILED'
    );
  }

  return {
    uri: finalUri,
    mime_type: mimeType,
    file_type: fileType,
  };
}

/**
 * Delete only temporary CV files created by downloadEmployerApplicantCV.
 */
export async function deleteTemporaryEmployerApplicantCV(
  uri: string
): Promise<void> {
  const cacheDirectory = FileSystem.cacheDirectory;

  if (
    !cacheDirectory ||
    typeof uri !== 'string' ||
    !uri.startsWith(`${cacheDirectory}internmatch-cv-`)
  ) {
    return;
  }

  await FileSystem.deleteAsync(
    uri,
    { idempotent: true }
  );
}


export type EmployerCandidateInsightResponse = {
  executive_summary: string;
  strengths: string[];
  gaps_to_validate: string[];
  interview_focus: string[];
  match_score: number | null;
  matching_skills: string[];
  missing_skills: string[];
  human_decision_required: boolean;
};

export type EmployerInterviewKitQuestion = {
  category:
    | 'technical'
    | 'experience'
    | 'project'
    | 'gap_validation'
    | 'role_context';
  question: string;
};

export type EmployerInterviewKitResponse = {
  questions: EmployerInterviewKitQuestion[];
  human_decision_required: boolean;
};

export async function getEmployerCandidateInsight(
  internshipId: string,
  applicationId: string,
  idempotencyKey: string,
  locale?: string
): Promise<EmployerCandidateInsightResponse> {
  const contentLocale = normalizeLocale(locale) || DEFAULT_LOCALE;

  return apiRequest<EmployerCandidateInsightResponse>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}/insight?content_locale=${encodeURIComponent(contentLocale)}`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    }
  );
}

export async function getEmployerInterviewKit(
  internshipId: string,
  applicationId: string,
  idempotencyKey: string,
  locale?: string
): Promise<EmployerInterviewKitResponse> {
  const contentLocale = normalizeLocale(locale) || DEFAULT_LOCALE;

  return apiRequest<EmployerInterviewKitResponse>(
    `/internships/${encodeURIComponent(internshipId)}/applicants/${encodeURIComponent(applicationId)}/interview-kit?content_locale=${encodeURIComponent(contentLocale)}`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    }
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

export async function deleteEmployerOpportunity(
  id: string
): Promise<void> {
  await apiRequest<void>(
    `/internships/${encodeURIComponent(id)}`,
    {
      method: 'DELETE',
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

export type AccountDeletionResponse = {
  deleted: boolean;
  message: string;
};

export async function deleteAccount(
  appleAuthorizationCode?: string | null
): Promise<AccountDeletionResponse> {
  const headers: Record<string, string> = {};

  if (appleAuthorizationCode) {
    headers['X-Apple-Authorization-Code'] =
      appleAuthorizationCode;
  }

  return apiRequest<AccountDeletionResponse>('/auth/account', {
    method: 'DELETE',
    headers,
  });
}

export type CancelProcessingJobResponse = {
  job_id: string;
  status: 'cancelled';
  message: string;
};

export async function cancelProcessingJob(
  jobId: string
): Promise<CancelProcessingJobResponse> {
  return apiRequest<CancelProcessingJobResponse>(
    `/jobs/${encodeURIComponent(jobId)}/cancel`,
    {
      method: 'POST',
    }
  );
}

export type EmployerComplianceClaimType =
  | 'insurance_arrangement'
  | 'completion_certificate'
  | 'university_agreement'
  | 'legal_internship_eligibility';

export type EmployerComplianceClaimStatus =
  | 'draft'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'revoked'
  | 'expired';

export type EmployerComplianceEvidence = {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type EmployerComplianceClaim = {
  id: string;
  organization_id: string;
  claim_type: EmployerComplianceClaimType;
  jurisdiction_country_code: string;
  scope_key: string;
  scope_label: string | null;
  statement: string | null;
  status: EmployerComplianceClaimStatus;
  version: number;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason_code: string | null;
  valid_from: string | null;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
  evidence: EmployerComplianceEvidence[];
};

export type EmployerComplianceCreatePayload = {
  claim_type: EmployerComplianceClaimType;
  jurisdiction_country_code: string;
  scope_key?: string;
  scope_label?: string | null;
  statement?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
};

export type EmployerComplianceUpdatePayload = {
  expected_version: number;
  scope_label?: string | null;
  statement?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
};

export async function listEmployerComplianceClaims(
): Promise<EmployerComplianceClaim[]> {
  return apiRequest<EmployerComplianceClaim[]>(
    '/employer-compliance/claims',
    {
      method: 'GET',
    }
  );
}

export async function createEmployerComplianceClaim(
  payload: EmployerComplianceCreatePayload
): Promise<EmployerComplianceClaim> {
  return apiRequest<EmployerComplianceClaim>(
    '/employer-compliance/claims',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function updateEmployerComplianceClaim(
  claimId: string,
  payload: EmployerComplianceUpdatePayload
): Promise<EmployerComplianceClaim> {
  return apiRequest<EmployerComplianceClaim>(
    (
      '/employer-compliance/claims/'
      + encodeURIComponent(claimId)
    ),
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    }
  );
}

export async function uploadEmployerComplianceEvidence(
  claimId: string,
  expectedVersion: number,
  file: {
    uri: string;
    name: string;
    type?: string;
  }
): Promise<EmployerComplianceClaim> {
  const formData = new FormData();

  appendReactNativeFile(
    formData,
    'file',
    {
      uri: file.uri,
      name: file.name,
      type: file.type || 'application/pdf',
    }
  );

  return apiRequest<EmployerComplianceClaim>(
    (
      '/employer-compliance/claims/'
      + encodeURIComponent(claimId)
      + '/evidence?expected_version='
      + encodeURIComponent(
        expectedVersion.toString()
      )
    ),
    {
      method: 'POST',
      body: formData,
    }
  );
}

export type EmployerComplianceLocalEvidence = {
  uri: string;
  mime_type: string;
};

export async function downloadEmployerComplianceEvidence(
  claimId: string,
  evidenceId: string
): Promise<EmployerComplianceLocalEvidence> {
  if (!apiBaseUrl) {
    throw new ApiError(
      'EXPO_PUBLIC_API_URL is not configured.',
      0,
      'API_NOT_CONFIGURED'
    );
  }

  const token = await getAccessToken();

  const path =
    '/employer-compliance/claims/'
    + encodeURIComponent(claimId)
    + '/evidence/'
    + encodeURIComponent(evidenceId)
    + '/content';

  const url = apiBaseUrl + path;

  if (/supabase\.co/i.test(url)) {
    throw new ApiError(
      'Provider URLs are not permitted for compliance evidence.',
      0,
      'PROVIDER_URL_BLOCKED'
    );
  }

  const cacheDirectory = FileSystem.cacheDirectory;

  if (!cacheDirectory) {
    throw new ApiError(
      'Temporary file storage is unavailable.',
      0,
      'FILE_CACHE_UNAVAILABLE'
    );
  }

  const safeEvidenceId =
    evidenceId.replace(/[^a-zA-Z0-9-]/g, '');

  const uri =
    `${cacheDirectory}internmatch-evidence-`
    + `${Date.now()}-${safeEvidenceId}.pdf`;

  let result;

  try {
    result = await FileSystem.downloadAsync(
      url,
      uri,
      {
        headers: {
          Authorization: 'Bearer ' + token,
        },
      }
    );
  } catch {
    await FileSystem.deleteAsync(
      uri,
      { idempotent: true }
    ).catch(() => {});

    throw new ApiError(
      'Compliance evidence download failed.',
      0,
      'EVIDENCE_DOWNLOAD_FAILED'
    );
  }

  if (result.status < 200 || result.status >= 300) {
    await FileSystem.deleteAsync(
      result.uri,
      { idempotent: true }
    ).catch(() => {});

    throw new ApiError(
      'Compliance evidence access was rejected.',
      result.status,
      'EVIDENCE_DOWNLOAD_REJECTED'
    );
  }

  return {
    uri: result.uri,
    mime_type: 'application/pdf',
  };
}

export async function deleteTemporaryComplianceEvidence(
  uri: string
): Promise<void> {
  const cacheDirectory = FileSystem.cacheDirectory;

  if (
    !cacheDirectory
    || !uri.startsWith(
      `${cacheDirectory}internmatch-evidence-`
    )
  ) {
    return;
  }

  await FileSystem.deleteAsync(
    uri,
    { idempotent: true }
  );
}


export async function submitEmployerComplianceClaim(
  claimId: string,
  expectedVersion: number
): Promise<EmployerComplianceClaim> {
  return apiRequest<EmployerComplianceClaim>(
    (
      '/employer-compliance/claims/'
      + encodeURIComponent(claimId)
      + '/submit'
    ),
    {
      method: 'POST',
      body: JSON.stringify({
        expected_version: expectedVersion,
      }),
    }
  );
}


type BrokeredAvatarDescriptor = {
  version: string;
  extension: 'jpg' | 'png' | 'webp';
};

function parseBrokeredAvatarUrl(
  value: string
): BrokeredAvatarDescriptor | null {
  if (
    !value.startsWith(
      '/api/v1/profile/avatar/content'
    )
  ) {
    return null;
  }

  const versionMatch =
    /[?&]v=([a-f0-9]{16})(?:&|$)/i.exec(
      value
    );

  const extensionMatch =
    /[?&]ext=(jpg|png|webp)(?:&|$)/i.exec(
      value
    );

  if (!versionMatch || !extensionMatch) {
    return null;
  }

  const extension =
    extensionMatch[1].toLowerCase();

  if (
    extension !== 'jpg'
    && extension !== 'png'
    && extension !== 'webp'
  ) {
    return null;
  }

  return {
    version:
      versionMatch[1].toLowerCase(),
    extension,
  };
}

async function materializeBrokeredAvatar(
  avatarUrl: string
): Promise<string | null> {
  if (/supabase\.co/i.test(avatarUrl)) {
    return null;
  }

  const descriptor =
    parseBrokeredAvatarUrl(avatarUrl);

  if (!descriptor) {
    return avatarUrl.startsWith('file://')
      ? avatarUrl
      : null;
  }

  if (!apiBaseUrl) {
    return null;
  }

  const cacheDirectory =
    FileSystem.cacheDirectory;

  if (!cacheDirectory) {
    return null;
  }

  const filename =
    `internmatch-avatar-${descriptor.version}.`
    + descriptor.extension;

  const localUri =
    cacheDirectory + filename;

  try {
    const existing =
      await FileSystem.getInfoAsync(localUri);

    if (existing.exists) {
      return localUri;
    }
  } catch {
    // Continue with a fresh authenticated download.
  }

  try {
    const entries =
      await FileSystem.readDirectoryAsync(
        cacheDirectory
      );

    for (const entry of entries) {
      if (
        entry.startsWith('internmatch-avatar-')
        && entry !== filename
      ) {
        await FileSystem.deleteAsync(
          cacheDirectory + entry,
          { idempotent: true }
        ).catch(() => {});
      }
    }
  } catch {
    // Cache cleanup is best-effort only.
  }

  let token: string;

  try {
    token = await getAccessToken();
  } catch {
    return null;
  }

  const downloadUrl =
    apiBaseUrl
    + '/profile/avatar/content';

  let result;

  try {
    result = await FileSystem.downloadAsync(
      downloadUrl,
      localUri,
      {
        headers: {
          Authorization:
            'Bearer ' + token,
        },
      }
    );
  } catch {
    await FileSystem.deleteAsync(
      localUri,
      { idempotent: true }
    ).catch(() => {});

    return null;
  }

  if (
    result.status < 200
    || result.status >= 300
  ) {
    await FileSystem.deleteAsync(
      result.uri,
      { idempotent: true }
    ).catch(() => {});

    return null;
  }

  return result.uri;
}

async function hydrateAvatarInApiPayload<T>(
  payload: T
): Promise<T> {
  if (!isJsonRecord(payload)) {
    return payload;
  }

  const avatarValue =
    payload.avatar_url;

  if (avatarValue == null) {
    return payload;
  }

  if (typeof avatarValue !== 'string') {
    return {
      ...payload,
      avatar_url: null,
    } as T;
  }

  if (/supabase\.co/i.test(avatarValue)) {
    return {
      ...payload,
      avatar_url: null,
    } as T;
  }

  const localAvatarUri =
    await materializeBrokeredAvatar(
      avatarValue
    );

  return {
    ...payload,
    avatar_url: localAvatarUri,
  } as T;
}

/**
 * Central authenticated API boundary.
 *
 * Avatar broker references are materialized to private local cache
 * before any screen receives them. Screens therefore consume file://
 * URIs only and never receive provider storage URLs or bearer links.
 */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const payload =
    await rawApiRequest<T>(
      path,
      options
    );

  return hydrateAvatarInApiPayload(
    payload
  );
}


export type UserNotification = {
  id: string;
  event_type: string;
  entity_type: string | null;
  entity_id: string | null;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export type NotificationListResponse = {
  items: UserNotification[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
};

export async function getNotifications(
  limit = 30,
  offset = 0
): Promise<NotificationListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  return apiRequest<NotificationListResponse>(
    '/notifications?' + params.toString()
  );
}

export async function getNotificationUnreadCount(): Promise<{
  unread_count: number;
}> {
  return apiRequest<{ unread_count: number }>(
    '/notifications/unread-count'
  );
}

export async function markNotificationRead(
  notificationId: string
): Promise<UserNotification> {
  return apiRequest<UserNotification>(
    (
      '/notifications/'
      + encodeURIComponent(notificationId)
      + '/read'
    ),
    {
      method: 'POST',
    }
  );
}

export async function markAllNotificationsRead(): Promise<{
  updated: number;
  unread_count: number;
}> {
  return apiRequest<{
    updated: number;
    unread_count: number;
  }>(
    '/notifications/read-all',
    {
      method: 'POST',
    }
  );
}

export async function registerPushDevice(payload: {
  expo_push_token: string;
  platform: 'ios' | 'android';
  locale: string;
}): Promise<{ registered: boolean }> {
  return apiRequest<{ registered: boolean }>(
    '/notifications/devices',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function disablePushDevice(
  expoPushToken: string
): Promise<{ registered: boolean }> {
  return apiRequest<{ registered: boolean }>(
    '/notifications/devices',
    {
      method: 'DELETE',
      body: JSON.stringify({
        expo_push_token: expoPushToken,
      }),
    }
  );
}


// ---------------------------------------------------------------------
// Private one-time promotional access.
// No promo secret or campaign list is exposed to the mobile client.
// ---------------------------------------------------------------------

export type PromoCodeAudience =
  | 'student'
  | 'employer';

export type PromoCodeStatusResponse = {
  audience: PromoCodeAudience;
  used_once: boolean;
  status:
    | 'pending'
    | 'redeemed'
    | 'failed'
    | null;
  access_expires_at: string | null;
};

export type PromoCodeRedeemResponse = {
  outcome:
    | 'granted'
    | 'granted_sync_pending';
  audience: PromoCodeAudience;
  plan:
    | 'pro_student'
    | 'employer_pro';
  access_started_at: string;
  access_expires_at: string;
  sync_pending: boolean;
};

export async function getPromoCodeStatus():
Promise<PromoCodeStatusResponse> {
  return apiRequest<PromoCodeStatusResponse>(
    '/promo-codes/status'
  );
}

export async function redeemPromoCode(
  code: string
): Promise<PromoCodeRedeemResponse> {
  return apiRequest<PromoCodeRedeemResponse>(
    '/promo-codes/redeem',
    {
      method: 'POST',
      body: JSON.stringify({
        code,
      }),
    }
  );
}
