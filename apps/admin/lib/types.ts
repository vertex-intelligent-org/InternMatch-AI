export type VerificationStatus =
  | 'unverified'
  | 'pending'
  | 'verified'
  | 'rejected'
  | 'suspended';

export type OrganizationType =
  | 'company'
  | 'university_lab'
  | 'research_center';

export type VerificationMethod =
  | 'standard_company'
  | 'manual_admin';

export type EmployerOrganization = {
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
  organization_type: OrganizationType;
  verification_method: VerificationMethod | null;
  verification_status: VerificationStatus;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason_code: string | null;
  created_at: string;
  updated_at: string;
};

export type RejectionReasonCode =
  | 'company_not_found'
  | 'registration_mismatch'
  | 'domain_mismatch'
  | 'email_not_professional'
  | 'insufficient_evidence'
  | 'suspected_impersonation'
  | 'other';

export type AdminApprovalPayload = {
  organization_type: OrganizationType;
  verification_method: VerificationMethod;
  internal_note?: string | null;
};

export type AdminRejectionPayload = {
  reason_code: RejectionReasonCode;
  internal_note?: string | null;
};

export type AdminSuspensionPayload = {
  reason_code: string;
  internal_note?: string | null;
};
export type PublicationStatus =
  | 'draft'
  | 'under_review'
  | 'published'
  | 'closed';

export type AdminInternshipSummary = {
  id: string;
  title: string;
  company: string;
  location: string;
  work_type: string;
  required_skills: string[];
  preferred_skills: string[];
  publication_status: PublicationStatus;
  is_active: boolean;
  posted_at: string;
};

export type AdminInternshipDetail =
  AdminInternshipSummary & {
    admin_managed: boolean;
    description: string;
    languages: string[];
    min_education: string | null;
    experience_requirements: string | null;
  };

export type AdminInternshipListResponse = {
  items: AdminInternshipSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminInternshipCreatePayload = {
  title: string;
  company: string;
  location: string;
  work_type: 'remote' | 'onsite' | 'hybrid';
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  language: string | null;
  education_requirements: string | null;
  experience_requirements: string | null;
  publication_status: 'draft' | 'published';
};

export type AdminApplicationStatus =
  | 'applied'
  | 'interviewing'
  | 'accepted'
  | 'rejected';

export type AdminApplicantCandidate = {
  student_id: string;
  full_name: string;
  headline: string | null;
  department: string | null;
  skills: string[];
};

export type AdminApplicantSkillEvidence = {
  name: string;
  cv_evidenced: boolean;
  self_declared: boolean;
  cv_provenance_known: boolean;
};

export type AdminApplicantItem = {
  application_id: string;
  internship_id: string;
  status: AdminApplicationStatus;
  applied_date: string | null;
  generated_cover_letter: string | null;
  match_score: number | null;
  skill_score: number | null;
  vector_score: number | null;
  attribute_score: number | null;
  ai_rank: number | null;
  matching_skills: string[];
  missing_skills: string[];
  skill_evidence: AdminApplicantSkillEvidence[];
  interview_scheduled_at: string | null;
  interview_mode: 'online' | 'onsite' | null;
  interview_location: string | null;
  interview_message: string | null;
  created_at: string;
  updated_at: string;
  candidate: AdminApplicantCandidate;
};

export type AdminApplicantListResponse = {
  items: AdminApplicantItem[];
  total: number;
  internship_id: string;
};

export type AdminApplicantStatusPayload = {
  status:
    | 'interviewing'
    | 'accepted'
    | 'rejected';
  notes?: string;
};

export type AdminInterviewSchedulePayload = {
  scheduled_at: string;
  mode: 'online' | 'onsite';
  location: string;
  message?: string | null;
};

export type AdminUserRole =
  | 'student'
  | 'employer';

export type AdminAuditSource =
  | 'employer_verification'
  | 'employer_compliance';

export type AdminUserSummary = {
  user_id: string;
  roles: AdminUserRole[];
  display_name: string;
  headline: string | null;
  business_email: string | null;
  organization_id: string | null;
  verification_status: string | null;
  organization_type: string | null;
  country_code: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminUserListResponse = {
  items: AdminUserSummary[];
  total: number;
  offset: number;
  limit: number;
};

export type AdminUserAuditEvent = {
  source: AdminAuditSource;
  related_id: string;
  actor_user_id: string | null;
  action: string;
  previous_status: string | null;
  new_status: string | null;
  reason_code: string | null;
  internal_note: string | null;
  created_at: string;
};

export type AdminUserDetail =
  AdminUserSummary & {
    audit_events: AdminUserAuditEvent[];
  };


// Employer compliance evidence is intentionally independent from
// organization identity verification.
export type ComplianceClaimStatus =
  | 'draft'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'revoked'
  | 'expired';

export type ComplianceClaimType =
  | 'insurance_arrangement'
  | 'completion_certificate'
  | 'university_agreement'
  | 'legal_internship_eligibility';

export type EmployerComplianceEvidence = {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  [key: string]: unknown;
};

export type EmployerComplianceClaim = {
  id: string;
  organization_id: string;
  claim_type: ComplianceClaimType;
  jurisdiction_country_code: string;
  scope_key: string;
  scope_label: string | null;
  statement: string | null;
  status: ComplianceClaimStatus;
  version: number;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason_code: string | null;
  valid_from: string | null;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
  evidence: EmployerComplianceEvidence[];
  [key: string]: unknown;
};

export type ComplianceAdminApprovalPayload = {
  expected_version: number;
  internal_note?: string | null;
};

export type ComplianceAdminRejectionPayload = {
  expected_version: number;
  reason_code: string;
  internal_note?: string | null;
};

export type ComplianceAdminRevocationPayload = {
  expected_version: number;
  reason_code: string;
  internal_note?: string | null;
};
