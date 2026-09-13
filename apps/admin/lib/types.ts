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
