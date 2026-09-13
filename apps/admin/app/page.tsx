'use client';

import {
  useEffect,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  approveOrganization,
  getOrganizationForReview,
  listOrganizationsForReview,
  rejectOrganization,
  suspendOrganization,
} from '../lib/api';
import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../lib/supabase';
import type {
  EmployerOrganization,
  OrganizationType,
  RejectionReasonCode,
  VerificationMethod,
  VerificationStatus,
} from '../lib/types';

type DashboardState =
  | 'loading'
  | 'ready'
  | 'denied'
  | 'error';

type ActionMode =
  | 'approve'
  | 'reject'
  | 'suspend'
  | null;

const verificationStatuses: VerificationStatus[] = [
  'unverified',
  'pending',
  'verified',
  'rejected',
  'suspended',
];

const organizationTypes: OrganizationType[] = [
  'company',
  'university_lab',
  'research_center',
];

const rejectionReasons: RejectionReasonCode[] = [
  'company_not_found',
  'registration_mismatch',
  'domain_mismatch',
  'email_not_professional',
  'insufficient_evidence',
  'suspected_impersonation',
  'other',
];

function isVerificationStatus(
  value: string
): value is VerificationStatus {
  return verificationStatuses.some(
    (candidate) => candidate === value
  );
}

function isOrganizationType(
  value: string
): value is OrganizationType {
  return organizationTypes.some(
    (candidate) => candidate === value
  );
}

function isVerificationMethod(
  value: string
): value is VerificationMethod {
  return (
    value === 'standard_company'
    || value === 'manual_admin'
  );
}

function isRejectionReason(
  value: string
): value is RejectionReasonCode {
  return rejectionReasons.some(
    (candidate) => candidate === value
  );
}

function formatDate(
  value: string | null
): string {
  if (!value) {
    return '?';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(
    'en',
    {
      dateStyle: 'medium',
      timeStyle: 'short',
    }
  ).format(date);
}

function errorMessage(
  error: unknown
): string {
  if (error instanceof AdminConfigurationError) {
    return (
      'The admin workspace is not fully '
      + 'configured on this device yet. '
      + 'Please check the local admin setup '
      + 'and try again.'
    );
  }

  if (error instanceof ApiError) {
    if (
      error.code === 'API_NOT_CONFIGURED'
    ) {
      return (
        'The admin service is not connected '
        + 'yet. Complete the local admin '
        + 'configuration, then try again.'
      );
    }

    if (
      error.code === 'NETWORK_ERROR'
      || error.status === 0
    ) {
      return (
        'The InternMatch admin service is '
        + 'temporarily unreachable. Make sure '
        + 'the API is running, then tap Refresh.'
      );
    }

    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return (
    'Something went wrong while loading the '
    + 'admin workspace. Please try again.'
  );
}

function humanize(
  value: string | null
): string {
  if (!value) {
    return '?';
  }

  return value
    .split('_')
    .map(
      (part) => (
        part.charAt(0).toUpperCase()
        + part.slice(1)
      )
    )
    .join(' ');
}

function statusBadgeClass(
  status: VerificationStatus
): string {
  switch (status) {
    case 'pending':
      return 'badge badgePending';

    case 'verified':
      return 'badge badgeVerified';

    case 'rejected':
      return 'badge badgeRejected';

    case 'suspended':
      return 'badge badgeSuspended';

    default:
      return 'badge badgeNeutral';
  }
}

export default function AdminDashboardPage() {
  const router = useRouter();

  const [dashboardState, setDashboardState] =
    useState<DashboardState>('loading');

  const [adminEmail, setAdminEmail] =
    useState('');

  const [selectedStatus, setSelectedStatus] =
    useState<VerificationStatus>('pending');

  const [organizations, setOrganizations] =
    useState<EmployerOrganization[]>([]);

  const [selectedId, setSelectedId] =
    useState<string | null>(null);

  const [selected, setSelected] =
    useState<EmployerOrganization | null>(
      null
    );

  const [queueError, setQueueError] =
    useState<string | null>(null);

  const [detailError, setDetailError] =
    useState<string | null>(null);

  const [refreshing, setRefreshing] =
    useState(false);

  const [detailLoading, setDetailLoading] =
    useState(false);

  const [actionMode, setActionMode] =
    useState<ActionMode>(null);

  const [actionSubmitting, setActionSubmitting] =
    useState(false);

  const [actionError, setActionError] =
    useState<string | null>(null);

  const [actionSuccess, setActionSuccess] =
    useState<string | null>(null);

  const [organizationType, setOrganizationType] =
    useState<OrganizationType>('company');

  const [verificationMethod, setVerificationMethod] =
    useState<VerificationMethod>(
      'standard_company'
    );

  const [approvalNote, setApprovalNote] =
    useState('');

  const [rejectionReason, setRejectionReason] =
    useState<RejectionReasonCode>(
      'insufficient_evidence'
    );

  const [rejectionNote, setRejectionNote] =
    useState('');

  const [suspensionReason, setSuspensionReason] =
    useState('');

  const [suspensionNote, setSuspensionNote] =
    useState('');

  function resetActionForm(
    organization?: EmployerOrganization | null
  ) {
    const nextType =
      organization?.organization_type
      ?? 'company';

    setActionMode(null);
    setActionError(null);
    setActionSuccess(null);

    setOrganizationType(nextType);

    setVerificationMethod(
      nextType === 'company'
        ? 'standard_company'
        : 'manual_admin'
    );

    setApprovalNote('');
    setRejectionReason(
      'insufficient_evidence'
    );
    setRejectionNote('');
    setSuspensionReason('');
    setSuspensionNote('');
  }

  async function handleProtectedFailure(
    error: unknown
  ): Promise<boolean> {
    if (!(error instanceof ApiError)) {
      return false;
    }

    if (error.status === 401) {
      try {
        await getSupabaseClient()
          .auth
          .signOut();
      } finally {
        router.replace('/login');
      }

      return true;
    }

    if (error.status === 403) {
      setDashboardState('denied');
      setQueueError(null);
      setDetailError(null);
      setOrganizations([]);
      setSelected(null);
      setSelectedId(null);
      resetActionForm(null);

      return true;
    }

    return false;
  }

  async function loadDetail(
    organizationId: string
  ) {
    setSelectedId(organizationId);
    setDetailLoading(true);
    setDetailError(null);
    setActionError(null);
    setActionSuccess(null);

    try {
      const organization =
        await getOrganizationForReview(
          organizationId
        );

      setSelected(organization);
      resetActionForm(organization);
    } catch (error) {
      const handled =
        await handleProtectedFailure(error);

      if (!handled) {
        setDetailError(
          errorMessage(error)
        );
      }
    } finally {
      setDetailLoading(false);
    }
  }

  async function loadQueue(
    status: VerificationStatus,
    preferredId: string | null
  ) {
    setRefreshing(true);
    setQueueError(null);

    try {
      const queue =
        await listOrganizationsForReview(
          status
        );

      setOrganizations(queue);
      setDashboardState('ready');

      const preferredStillExists =
        preferredId !== null
        && queue.some(
          (item) => (
            item.id === preferredId
          )
        );

      if (
        preferredStillExists
        && preferredId
      ) {
        await loadDetail(preferredId);
      } else if (queue.length > 0) {
        await loadDetail(queue[0].id);
      } else {
        setSelectedId(null);
        setSelected(null);
        setDetailError(null);
        resetActionForm(null);
      }
    } catch (error) {
      const handled =
        await handleProtectedFailure(error);

      if (!handled) {
        setQueueError(
          errorMessage(error)
        );
        setDashboardState('error');
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function refreshQueue() {
    await loadQueue(
      selectedStatus,
      selectedId
    );
  }

  useEffect(() => {
    let active = true;

    async function initialize() {
      try {
        const supabase =
          getSupabaseClient();

        const {
          data,
          error: sessionError,
        } = await supabase.auth.getSession();

        if (!active) {
          return;
        }

        if (sessionError) {
          setQueueError(
            sessionError.message
          );
          setDashboardState('error');
          return;
        }

        if (!data.session) {
          router.replace('/login');
          return;
        }

        setAdminEmail(
          data.session.user.email
          ?? 'Authorized administrator'
        );

        try {
          const queue =
            await listOrganizationsForReview(
              'pending'
            );

          if (!active) {
            return;
          }

          setOrganizations(queue);
          setDashboardState('ready');

          if (queue.length > 0) {
            const first =
              await getOrganizationForReview(
                queue[0].id
              );

            if (active) {
              setSelectedId(first.id);
              setSelected(first);
              resetActionForm(first);
            }
          }
        } catch (requestError) {
          if (!active) {
            return;
          }

          if (
            requestError instanceof ApiError
            && requestError.status === 401
          ) {
            await supabase.auth.signOut();

            if (active) {
              router.replace('/login');
            }

            return;
          }

          if (
            requestError instanceof ApiError
            && requestError.status === 403
          ) {
            setDashboardState('denied');
            return;
          }

          setQueueError(
            errorMessage(requestError)
          );
          setDashboardState('error');
        }
      } catch (configurationError) {
        if (active) {
          setQueueError(
            errorMessage(
              configurationError
            )
          );
          setDashboardState('error');
        }
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, [router]);

  async function signOut() {
    try {
      await getSupabaseClient()
        .auth
        .signOut();
    } finally {
      router.replace('/login');
    }
  }

  async function executeMutation(
    mutation: () => Promise<EmployerOrganization>,
    successMessage: string
  ) {
    setActionSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      await mutation();

      await loadQueue(
        selectedStatus,
        null
      );

      setActionSuccess(
        successMessage
      );
    } catch (error) {
      const handled =
        await handleProtectedFailure(error);

      if (handled) {
        return;
      }

      if (
        error instanceof ApiError
        && error.status === 409
      ) {
        await loadQueue(
          selectedStatus,
          selectedId
        );

        setActionError(
          error.message
        );

        return;
      }

      setActionError(
        errorMessage(error)
      );
    } finally {
      setActionSubmitting(false);
    }
  }

  async function handleApprove() {
    if (
      !selected
      || selected.verification_status
        !== 'pending'
    ) {
      return;
    }

    const note =
      approvalNote.trim();

    if (
      organizationType !== 'company'
      && verificationMethod
        !== 'manual_admin'
    ) {
      setActionError(
        'University labs and research centers require manual administrative verification.'
      );
      return;
    }

    if (
      verificationMethod === 'manual_admin'
      && !note
    ) {
      setActionError(
        'Manual administrative verification requires an internal review note.'
      );
      return;
    }

    const confirmed = window.confirm(
      (
        'Approve '
        + selected.display_name
        + ' as '
        + humanize(organizationType)
        + '?'
      )
    );

    if (!confirmed) {
      return;
    }

    await executeMutation(
      () => approveOrganization(
        selected.id,
        {
          organization_type:
            organizationType,
          verification_method:
            verificationMethod,
          internal_note:
            note || null,
        }
      ),
      (
        selected.display_name
        + ' was approved.'
      )
    );
  }

  async function handleReject() {
    if (
      !selected
      || selected.verification_status
        !== 'pending'
    ) {
      return;
    }

    const confirmed = window.confirm(
      (
        'Reject '
        + selected.display_name
        + '?'
      )
    );

    if (!confirmed) {
      return;
    }

    const note =
      rejectionNote.trim();

    await executeMutation(
      () => rejectOrganization(
        selected.id,
        {
          reason_code:
            rejectionReason,
          internal_note:
            note || null,
        }
      ),
      (
        selected.display_name
        + ' was rejected.'
      )
    );
  }

  async function handleSuspend() {
    if (
      !selected
      || selected.verification_status
        !== 'verified'
    ) {
      return;
    }

    const reason =
      suspensionReason.trim();

    if (!reason) {
      setActionError(
        'Suspension requires a reason code.'
      );
      return;
    }

    const confirmed = window.confirm(
      (
        'Suspend '
        + selected.display_name
        + '? This immediately closes current employer-owned opportunities.'
      )
    );

    if (!confirmed) {
      return;
    }

    const note =
      suspensionNote.trim();

    await executeMutation(
      () => suspendOrganization(
        selected.id,
        {
          reason_code: reason,
          internal_note:
            note || null,
        }
      ),
      (
        selected.display_name
        + ' was suspended.'
      )
    );
  }

  if (dashboardState === 'loading') {
    return (
      <main className="centeredState">
        <div className="stateCard">
          <span
            className="spinner"
            aria-hidden="true"
          />
          <strong>
            Verifying administrator session
          </strong>
          <span>
            Waiting for server authorization?
          </span>
        </div>
      </main>
    );
  }

  if (dashboardState === 'denied') {
    return (
      <main className="centeredState">
        <section className="stateCard">
          <span className="deniedIcon">
            !
          </span>
          <strong>
            Administrative access denied
          </strong>
          <span>
            Your account is authenticated, but
            the InternMatch API did not authorize
            it as an administrator.
          </span>
          <button
            className="button buttonSecondary"
            type="button"
            onClick={() => {
              void signOut();
            }}
          >
            Sign out
          </button>
        </section>
      </main>
    );
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">
            IM
          </span>
          <div>
            <strong>InternMatch</strong>
            <span>Trust Console</span>
          </div>
        </div>

        <nav
          className="sidebarSection"
          aria-label="Administration"
        >
          <p className="sidebarLabel">
            Trust & Safety
          </p>

          <span className="sidebarLink sidebarLinkActive">
            <span>
              Organization reviews
            </span>
            <span className="navCount">
              {organizations.length}
            </span>
          </span>
        </nav>

        <div className="sidebarFooter">
          <div className="adminIdentity">
            <span className="adminAvatar">
              A
            </span>
            <div>
              <strong>Administrator</strong>
              <span>{adminEmail}</span>
            </div>
          </div>

          <button
            className="button buttonGhost"
            type="button"
            onClick={() => {
              void signOut();
            }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">
              InternMatch Admin / Trust & Safety
            </p>
            <h1>
              Welcome back
            </h1>
            <p>
              Keep the InternMatch community
              trusted by reviewing one
              organization at a time.
            </p>
          </div>

          <div className="topbarActions">
            <label className="statusFilter">
              <span>Status</span>
              <select
                className="select"
                value={selectedStatus}
                disabled={
                  refreshing
                  || actionSubmitting
                }
                onChange={(event) => {
                  const value =
                    event.target.value;

                  if (
                    !isVerificationStatus(
                      value
                    )
                  ) {
                    return;
                  }

                  setSelectedStatus(value);
                  setSelectedId(null);
                  setSelected(null);
                  resetActionForm(null);

                  void loadQueue(
                    value,
                    null
                  );
                }}
              >
                {verificationStatuses.map(
                  (status) => (
                    <option
                      key={status}
                      value={status}
                    >
                      {humanize(status)}
                    </option>
                  )
                )}
              </select>
            </label>

            <span className="statusPill">
              Secure review
            </span>

            <button
              className="button buttonSecondary"
              type="button"
              disabled={
                refreshing
                || actionSubmitting
              }
              onClick={() => {
                void refreshQueue();
              }}
            >
              {refreshing
                ? 'Refreshing...'
                : 'Refresh'}
            </button>
          </div>
        </header>

        <section
          className="welcomeStrip"
          aria-label="Admin workspace guidance"
        >
          <div className="welcomeIntro">
            <span
              className="welcomeIcon"
              aria-hidden="true"
            >
              IM
            </span>

            <div>
              <span className="welcomeKicker">
                Your trust workspace
              </span>

              <strong>
                {
                  humanize(selectedStatus)
                }
                {' '}
                reviews
              </strong>

              <p>
                {
                  organizations.length
                }
                {' '}
                organization
                {
                  organizations.length === 1
                    ? ''
                    : 's'
                }
                {' '}
                currently visible. Choose one
                and review the evidence before
                taking action.
              </p>
            </div>
          </div>

          <div
            className="welcomeSteps"
            aria-label="Review workflow"
          >
            <span>
              <b>1</b>
              Review evidence
            </span>

            <span>
              <b>2</b>
              Confirm decision
            </span>

            <span>
              <b>3</b>
              InternMatch applies it securely
            </span>
          </div>
        </section>

        {queueError ? (
          <div
            className="errorBox"
            role="alert"
          >
            {queueError}
          </div>
        ) : null}

        {actionSuccess ? (
          <div
            className="successBox pageMessage"
            role="status"
          >
            {actionSuccess}
          </div>
        ) : null}

        <section className="contentGrid">
          <div className="panel queuePanel">
            <div className="panelHeader">
              <div>
                <h2>
                  {humanize(selectedStatus)}
                  {' '}
                  organizations
                </h2>
                <p>
                  {organizations.length}
                  {' '}
                  organization
                  {organizations.length === 1
                    ? ''
                    : 's'}
                </p>
              </div>
            </div>

            {queueError ? (
              <div className="emptyState">
                <strong>
                  We could not load this list yet
                </strong>
                <span>
                  Check the admin connection,
                  then tap Refresh to try again.
                </span>
              </div>
            ) : organizations.length === 0 ? (
              <div className="emptyState">
                <strong>
                  {
                    selectedStatus === 'pending'
                      ? "You're all caught up"
                      : 'Nothing here yet'
                  }
                </strong>
                <span>
                  {
                    selectedStatus === 'pending'
                      ? 'There are no organizations waiting for verification right now.'
                      : (
                        'No organizations currently have the '
                        + humanize(selectedStatus).toLowerCase()
                        + ' status.'
                      )
                  }
                </span>
              </div>
            ) : (
              <div className="queueList">
                {organizations.map(
                  (organization) => (
                    <button
                      key={organization.id}
                      className={
                        (
                          'queueButton '
                          + (
                            selectedId
                            === organization.id
                              ? 'queueButtonActive'
                              : ''
                          )
                        )
                      }
                      type="button"
                      aria-pressed={
                        selectedId
                        === organization.id
                      }
                      disabled={
                        actionSubmitting
                      }
                      onClick={() => {
                        void loadDetail(
                          organization.id
                        );
                      }}
                    >
                      <span className="queueTopline">
                        <strong className="orgName">
                          {
                            organization
                              .display_name
                          }
                        </strong>

                        <span
                          className={
                            statusBadgeClass(
                              organization
                                .verification_status
                            )
                          }
                        >
                          {
                            humanize(
                              organization
                                .verification_status
                            )
                          }
                        </span>
                      </span>

                      <span className="orgMeta">
                        {
                          organization
                            .normalized_domain
                        }
                      </span>

                      <span className="orgMeta">
                        {
                          organization
                            .business_email
                        }
                      </span>

                      <span className="queueFooter">
                        <span>
                          {
                            humanize(
                              organization
                                .organization_type
                            )
                          }
                        </span>

                        <span>
                          Updated
                          {' '}
                          {
                            formatDate(
                              organization
                                .updated_at
                            )
                          }
                        </span>
                      </span>
                    </button>
                  )
                )}
              </div>
            )}
          </div>

          <div className="panel detailPanel">
            <div className="panelHeader">
              <div>
                <h2>
                  Organization details
                </h2>
                <p>
                  Review the evidence, identity
                  details, and available action.
                </p>
              </div>

              {selected ? (
                <span
                  className={
                    statusBadgeClass(
                      selected
                        .verification_status
                    )
                  }
                >
                  {
                    humanize(
                      selected
                        .verification_status
                    )
                  }
                </span>
              ) : null}
            </div>

            {detailLoading ? (
              <div className="emptyState">
                <span
                  className="spinner"
                  aria-hidden="true"
                />
                <span>
                  Loading authoritative details...
                </span>
              </div>
            ) : detailError ? (
              <div
                className="errorBox detailMessage"
                role="alert"
              >
                {detailError}
              </div>
            ) : !selected ? (
              <div className="emptyState">
                <strong>
                  Select an organization
                </strong>
                <span>
                  Tap an organization to review
                  its evidence and available
                  actions.
                </span>
              </div>
            ) : (
              <>
                <div className="detailHero">
                  <div>
                    <p className="eyebrow">
                      {
                        humanize(
                          selected
                            .organization_type
                        )
                      }
                    </p>

                    <h3>
                      {selected.display_name}
                    </h3>

                    <p>
                      {selected.legal_name}
                    </p>
                  </div>

                  <a
                    className="button buttonSecondary"
                    href={selected.website_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open website
                  </a>
                </div>

                <div className="detailGrid">
                  <div className="field">
                    <span className="label">
                      Domain
                    </span>
                    <span className="value">
                      {
                        selected
                          .normalized_domain
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Country
                    </span>
                    <span className="value">
                      {selected.country_code}
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Business email
                    </span>
                    <span className="value">
                      {selected.business_email}
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Email/domain evidence
                    </span>
                    <span
                      className={
                        selected
                          .email_domain_matches_website
                          ? 'booleanGood'
                          : 'booleanBad'
                      }
                    >
                      {
                        selected
                          .email_domain_matches_website
                          ? 'Domain matches'
                          : 'Domain mismatch'
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Organization type
                    </span>
                    <span className="value">
                      {
                        humanize(
                          selected
                            .organization_type
                        )
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Verification method
                    </span>
                    <span className="value">
                      {
                        humanize(
                          selected
                            .verification_method
                        )
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Registration number
                    </span>
                    <span className="value">
                      {
                        selected
                          .registration_number
                        ?? '?'
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Tax number
                    </span>
                    <span className="value">
                      {
                        selected.tax_number
                        ?? '?'
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Representative
                    </span>
                    <span className="value">
                      {
                        selected
                          .representative_name
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Representative role
                    </span>
                    <span className="value">
                      {
                        selected
                          .representative_role
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Submitted
                    </span>
                    <span className="value">
                      {
                        formatDate(
                          selected
                            .submitted_at
                        )
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Reviewed
                    </span>
                    <span className="value">
                      {
                        formatDate(
                          selected
                            .reviewed_at
                        )
                      }
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Rejection reason
                    </span>
                    <span className="value">
                      {
                        humanize(
                          selected
                            .rejection_reason_code
                        )
                      }
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Organization ID
                    </span>
                    <code className="codeValue">
                      {selected.id}
                    </code>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Owner user ID
                    </span>
                    <code className="codeValue">
                      {selected.owner_user_id}
                    </code>
                  </div>
                </div>

                <section className="actionPanel">
                  <div className="actionPanelHeader">
                    <div>
                      <p className="eyebrow">
                        Administrative action
                      </p>
                      <h3>
                        Trust decision
                      </h3>
                    </div>

                    <span
                      className={
                        statusBadgeClass(
                          selected
                            .verification_status
                        )
                      }
                    >
                      {
                        humanize(
                          selected
                            .verification_status
                        )
                      }
                    </span>
                  </div>

                  {actionError ? (
                    <div
                      className="errorBox actionMessage"
                      role="alert"
                    >
                      {actionError}
                    </div>
                  ) : null}

                  {selected.verification_status
                    === 'pending' ? (
                    <>
                      <div className="actionTabs">
                        <button
                          className={
                            (
                              'button '
                              + (
                                actionMode
                                === 'approve'
                                  ? 'buttonPrimary'
                                  : 'buttonSecondary'
                              )
                            )
                          }
                          type="button"
                          disabled={
                            actionSubmitting
                          }
                          onClick={() => {
                            setActionMode(
                              'approve'
                            );
                            setActionError(
                              null
                            );
                          }}
                        >
                          Approve
                        </button>

                        <button
                          className={
                            (
                              'button '
                              + (
                                actionMode
                                === 'reject'
                                  ? 'buttonDanger'
                                  : 'buttonSecondary'
                              )
                            )
                          }
                          type="button"
                          disabled={
                            actionSubmitting
                          }
                          onClick={() => {
                            setActionMode(
                              'reject'
                            );
                            setActionError(
                              null
                            );
                          }}
                        >
                          Reject
                        </button>
                      </div>

                      {actionMode
                        === 'approve' ? (
                        <div className="actionForm">
                          <div className="actionFormGrid">
                            <label className="formField">
                              <span>
                                Organization type
                              </span>
                              <select
                                className="input select"
                                value={
                                  organizationType
                                }
                                disabled={
                                  actionSubmitting
                                }
                                onChange={(event) => {
                                  const value =
                                    event.target.value;

                                  if (
                                    !isOrganizationType(
                                      value
                                    )
                                  ) {
                                    return;
                                  }

                                  setOrganizationType(
                                    value
                                  );

                                  if (
                                    value
                                    !== 'company'
                                  ) {
                                    setVerificationMethod(
                                      'manual_admin'
                                    );
                                  }
                                }}
                              >
                                <option value="company">
                                  Company
                                </option>
                                <option value="university_lab">
                                  University lab
                                </option>
                                <option value="research_center">
                                  Research center
                                </option>
                              </select>
                            </label>

                            <label className="formField">
                              <span>
                                Verification method
                              </span>
                              <select
                                className="input select"
                                value={
                                  verificationMethod
                                }
                                disabled={
                                  actionSubmitting
                                  || organizationType
                                    !== 'company'
                                }
                                onChange={(event) => {
                                  const value =
                                    event.target.value;

                                  if (
                                    isVerificationMethod(
                                      value
                                    )
                                  ) {
                                    setVerificationMethod(
                                      value
                                    );
                                  }
                                }}
                              >
                                <option value="standard_company">
                                  Standard company
                                </option>
                                <option value="manual_admin">
                                  Manual admin
                                </option>
                              </select>
                            </label>
                          </div>

                          <label className="formField">
                            <span>
                              Internal review note
                              {
                                verificationMethod
                                === 'manual_admin'
                                  ? ' *'
                                  : ''
                              }
                            </span>

                            <textarea
                              className="input textarea"
                              value={
                                approvalNote
                              }
                              disabled={
                                actionSubmitting
                              }
                              placeholder={
                                verificationMethod
                                === 'manual_admin'
                                  ? 'Document the institutional evidence used for manual verification.'
                                  : 'Optional internal verification notes.'
                              }
                              onChange={(event) => {
                                setApprovalNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              Reviewer identity and
                              reviewed time are set by
                              the server.
                            </span>

                            <button
                              className="button buttonPrimary"
                              type="button"
                              disabled={
                                actionSubmitting
                              }
                              onClick={() => {
                                void handleApprove();
                              }}
                            >
                              {
                                actionSubmitting
                                  ? 'Submitting...'
                                  : 'Approve organization'
                              }
                            </button>
                          </div>
                        </div>
                      ) : null}

                      {actionMode
                        === 'reject' ? (
                        <div className="actionForm">
                          <label className="formField">
                            <span>
                              Rejection reason
                            </span>

                            <select
                              className="input select"
                              value={
                                rejectionReason
                              }
                              disabled={
                                actionSubmitting
                              }
                              onChange={(event) => {
                                const value =
                                  event.target.value;

                                if (
                                  isRejectionReason(
                                    value
                                  )
                                ) {
                                  setRejectionReason(
                                    value
                                  );
                                }
                              }}
                            >
                              {
                                rejectionReasons.map(
                                  (reason) => (
                                    <option
                                      key={reason}
                                      value={reason}
                                    >
                                      {
                                        humanize(
                                          reason
                                        )
                                      }
                                    </option>
                                  )
                                )
                              }
                            </select>
                          </label>

                          <label className="formField">
                            <span>
                              Internal note
                            </span>

                            <textarea
                              className="input textarea"
                              value={
                                rejectionNote
                              }
                              disabled={
                                actionSubmitting
                              }
                              placeholder="Optional internal moderation context."
                              onChange={(event) => {
                                setRejectionNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              The organization may
                              correct its information
                              and resubmit later.
                            </span>

                            <button
                              className="button buttonDanger"
                              type="button"
                              disabled={
                                actionSubmitting
                              }
                              onClick={() => {
                                void handleReject();
                              }}
                            >
                              {
                                actionSubmitting
                                  ? 'Submitting...'
                                  : 'Reject organization'
                              }
                            </button>
                          </div>
                        </div>
                      ) : null}

                      {actionMode === null ? (
                        <div className="readOnlyNotice">
                          Choose an action when you are
                          ready. InternMatch validates
                          the decision before applying it.
                        </div>
                      ) : null}
                    </>
                  ) : selected.verification_status
                    === 'verified' ? (
                    <>
                      <div className="actionTabs">
                        <button
                          className={
                            (
                              'button '
                              + (
                                actionMode
                                === 'suspend'
                                  ? 'buttonDanger'
                                  : 'buttonSecondary'
                              )
                            )
                          }
                          type="button"
                          disabled={
                            actionSubmitting
                          }
                          onClick={() => {
                            setActionMode(
                              'suspend'
                            );
                            setActionError(
                              null
                            );
                          }}
                        >
                          Suspend organization
                        </button>
                      </div>

                      {actionMode
                        === 'suspend' ? (
                        <div className="actionForm">
                          <div className="dangerNotice">
                            Suspension immediately
                            closes current
                            employer-owned
                            opportunities. The backend
                            remains authoritative.
                          </div>

                          <label className="formField">
                            <span>
                              Suspension reason code *
                            </span>

                            <input
                              className="input"
                              type="text"
                              value={
                                suspensionReason
                              }
                              disabled={
                                actionSubmitting
                              }
                              placeholder="e.g. suspected_abuse"
                              onChange={(event) => {
                                setSuspensionReason(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <label className="formField">
                            <span>
                              Internal note
                            </span>

                            <textarea
                              className="input textarea"
                              value={
                                suspensionNote
                              }
                              disabled={
                                actionSubmitting
                              }
                              placeholder="Optional internal moderation evidence or context."
                              onChange={(event) => {
                                setSuspensionNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              Suspension reason codes
                              are server-validated as
                              required non-empty
                              strings.
                            </span>

                            <button
                              className="button buttonDanger"
                              type="button"
                              disabled={
                                actionSubmitting
                              }
                              onClick={() => {
                                void handleSuspend();
                              }}
                            >
                              {
                                actionSubmitting
                                  ? 'Submitting...'
                                  : 'Confirm suspension'
                              }
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="readOnlyNotice">
                      No action is needed for this
                      status right now. You can still
                      review all organization details.
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
