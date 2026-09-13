'use client';

import {
  useEffect,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  getOrganizationForReview,
  listOrganizationsForReview,
} from '../lib/api';
import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../lib/supabase';
import type {
  EmployerOrganization,
} from '../lib/types';

type DashboardState =
  | 'loading'
  | 'ready'
  | 'denied'
  | 'error';

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
  if (
    error instanceof ApiError
    || error instanceof AdminConfigurationError
    || error instanceof Error
  ) {
    return error.message;
  }

  return 'Unable to complete the request.';
}

function humanize(
  value: string | null
): string {
  if (!value) {
    return '?';
  }

  return value
    .split('_')
    .map((part) => (
      part.charAt(0).toUpperCase()
      + part.slice(1)
    ))
    .join(' ');
}

export default function AdminDashboardPage() {
  const router = useRouter();

  const [dashboardState, setDashboardState] =
    useState<DashboardState>('loading');

  const [adminEmail, setAdminEmail] =
    useState('');

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

    try {
      const organization =
        await getOrganizationForReview(
          organizationId
        );

      setSelected(organization);
    } catch (error) {
      const handled =
        await handleProtectedFailure(
          error
        );

      if (!handled) {
        setDetailError(
          errorMessage(error)
        );
      }
    } finally {
      setDetailLoading(false);
    }
  }

  async function refreshQueue() {
    setRefreshing(true);
    setQueueError(null);

    try {
      const queue =
        await listOrganizationsForReview(
          'pending'
        );

      setOrganizations(queue);
      setDashboardState('ready');

      const stillSelected =
        selectedId
        && queue.some(
          (item) => (
            item.id === selectedId
          )
        );

      if (
        stillSelected
        && selectedId
      ) {
        await loadDetail(selectedId);
      } else if (queue.length > 0) {
        await loadDetail(queue[0].id);
      } else {
        setSelectedId(null);
        setSelected(null);
        setDetailError(null);
      }
    } catch (error) {
      const handled =
        await handleProtectedFailure(
          error
        );

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
            <span>Admin Console</span>
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
              Verification queue
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
              Employer trust
            </p>
            <h1>
              Verification queue
            </h1>
            <p>
              Pending organizations waiting for
              administrative review.
            </p>
          </div>

          <div className="topbarActions">
            <span className="statusPill">
              Server-authorized
            </span>

            <button
              className="button buttonSecondary"
              type="button"
              disabled={refreshing}
              onClick={() => {
                void refreshQueue();
              }}
            >
              {refreshing
                ? 'Refreshing?'
                : 'Refresh'}
            </button>
          </div>
        </header>

        {queueError ? (
          <div
            className="errorBox"
            role="alert"
          >
            {queueError}
          </div>
        ) : null}

        <section className="contentGrid">
          <div className="panel queuePanel">
            <div className="panelHeader">
              <div>
                <h2>Pending review</h2>
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

            {organizations.length === 0 ? (
              <div className="emptyState">
                <strong>
                  Queue is clear
                </strong>
                <span>
                  There are no pending
                  organization reviews.
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
                        <span className="badge badgePending">
                          Pending
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
                          Submitted
                          {' '}
                          {
                            formatDate(
                              organization
                                .submitted_at
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
                  Read-only review context
                </p>
              </div>

              {selected ? (
                <span className="badge badgeNeutral">
                  {
                    humanize(
                      selected
                        .organization_type
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
                  Loading authoritative details?
                </span>
              </div>
            ) : detailError ? (
              <div
                className="errorBox"
                role="alert"
              >
                {detailError}
              </div>
            ) : !selected ? (
              <div className="emptyState">
                <strong>
                  No organization selected
                </strong>
                <span>
                  Choose an organization from
                  the queue to inspect it.
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
                            .verification_status
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
                      Created
                    </span>
                    <span className="value">
                      {
                        formatDate(
                          selected
                            .created_at
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

                <div className="readOnlyNotice">
                  Review actions are intentionally
                  disabled in A5B-1. Approval,
                  rejection, and suspension controls
                  are added only after this secure
                  read path is validated.
                </div>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
