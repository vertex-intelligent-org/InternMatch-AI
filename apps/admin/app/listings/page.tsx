'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  closeAdminInternship,
  deleteAdminInternship,
  getAdminInternship,
  listAdminInternships,
  reopenAdminInternship,

  approveAdminInternship,
  requestChangesAdminInternship,
} from '../../lib/api';
import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../../lib/supabase';
import type {
  AdminInternshipDetail,
  AdminInternshipSummary,
  PublicationStatus,
} from '../../lib/types';

type PageState =
  | 'loading'
  | 'ready'
  | 'denied'
  | 'error';

type StatusFilter =
  | 'all'
  | PublicationStatus;

const statuses: PublicationStatus[] = [
  'draft',
  'under_review',
  'published',
  'closed',
];

function humanize(value: string): string {
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

function formatDate(value: string): string {
  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminConfigurationError) {
    return (
      'The admin workspace is not fully '
      + 'configured on this device yet.'
    );
  }

  if (error instanceof ApiError) {
    if (
      error.code === 'NETWORK_ERROR'
      || error.status === 0
    ) {
      return (
        'The InternMatch admin service is '
        + 'temporarily unreachable.'
      );
    }

    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Unable to complete the request.';
}

function statusClass(
  status: PublicationStatus
): string {
  switch (status) {
    case 'published':
      return 'badge badgeVerified';

    case 'closed':
      return 'badge badgeSuspended';

    case 'under_review':
      return 'badge badgePending';

    default:
      return 'badge badgeNeutral';
  }
}

export default function AdminListingsPage() {
  const router = useRouter();

  const deleteMutationRef =
    useRef(false);

  const [pageState, setPageState] =
    useState<PageState>('loading');

  const [adminEmail, setAdminEmail] =
    useState('');

  const [selectedStatus, setSelectedStatus] =
    useState<StatusFilter>('all');

  const [listings, setListings] =
    useState<AdminInternshipSummary[]>([]);

  const [totalListings, setTotalListings] =
    useState(0);

  const [listOffset, setListOffset] =
    useState(0);

  const [selectedId, setSelectedId] =
    useState<string | null>(null);

  const [selected, setSelected] =
    useState<AdminInternshipDetail | null>(
      null
    );

  const [loadingList, setLoadingList] =
    useState(false);

  const [loadingDetail, setLoadingDetail] =
    useState(false);

  const [mutating, setMutating] =
    useState(false);

  const [pageError, setPageError] =
    useState<string | null>(null);

  const [detailError, setDetailError] =
    useState<string | null>(null);

  const [success, setSuccess] =
    useState<string | null>(null);

  const [
    employerVisibleFeedback,
    setEmployerVisibleFeedback,
  ] = useState('');

  const handleProtectedFailure =
    useCallback(
      async (
        error: unknown
      ): Promise<boolean> => {
        if (!(error instanceof ApiError)) {
          return false;
        }

        if (
          error.status !== 401
          && error.status !== 403
        ) {
          return false;
        }

        try {
          await getSupabaseClient()
            .auth
            .signOut();
        } finally {
          if (error.status === 403) {
            setPageState('denied');
          } else {
            router.replace('/login');
          }
        }

        return true;
      },
      [router]
    );

  const loadDetail =
    useCallback(
      async (
        id: string
      ): Promise<void> => {
        setSelectedId(id);
        setLoadingDetail(true);
        setDetailError(null);
        setEmployerVisibleFeedback('');

        try {
          const detail =
            await getAdminInternship(id);

          setSelected(detail);
        } catch (error) {
          const handled =
            await handleProtectedFailure(
              error
            );

          if (!handled) {
            setSelected(null);
            setDetailError(
              errorMessage(error)
            );
          }
        } finally {
          setLoadingDetail(false);
        }
      },
      [handleProtectedFailure]
    );

  const loadListings =
    useCallback(
      async (
        statusFilter: StatusFilter,
        preferredId: string | null,
        offset = 0
      ): Promise<void> => {
        setLoadingList(true);
        setPageError(null);

        try {
          const response =
            await listAdminInternships(
              statusFilter === 'all'
                ? undefined
                : statusFilter,
              20,
              offset
            );

          setListings(response.items);
          setTotalListings(response.total);
          setListOffset(response.offset);
          setPageState('ready');

          const preferredExists =
            preferredId !== null
            && response.items.some(
              (item) => (
                item.id === preferredId
              )
            );

          if (
            preferredExists
            && preferredId
          ) {
            await loadDetail(
              preferredId
            );
          } else if (
            response.items.length > 0
          ) {
            await loadDetail(
              response.items[0].id
            );
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
            setPageState('error');
            setPageError(
              errorMessage(error)
            );
          }
        } finally {
          setLoadingList(false);
        }
      },
      [
        handleProtectedFailure,
        loadDetail,
      ]
    );

  useEffect(() => {
    let active = true;

    async function initialize() {
      try {
        const supabase =
          getSupabaseClient();

        const {
          data,
          error,
        } = await supabase.auth.getSession();

        if (!active) {
          return;
        }

        if (error || !data.session) {
          router.replace('/login');
          return;
        }

        setAdminEmail(
          data.session.user.email
          ?? 'Authorized administrator'
        );

        await loadListings(
          'all',
          null
        );
      } catch (error) {
        if (!active) {
          return;
        }

        setPageState('error');
        setPageError(
          errorMessage(error)
        );
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, [
    loadListings,
    router,
  ]);

  async function signOut() {
    try {
      await getSupabaseClient()
        .auth
        .signOut();
    } finally {
      router.replace('/login');
    }
  }

  async function runMutation(
    action: () => Promise<AdminInternshipDetail>,
    successMessage: string
  ) {
    setMutating(true);
    setPageError(null);
    setSuccess(null);

    try {
      await action();

      await loadListings(
        selectedStatus,
        null
      );

      setSuccess(successMessage);
    } catch (error) {
      const handled =
        await handleProtectedFailure(error);

      if (!handled) {
        setPageError(
          errorMessage(error)
        );
      }
    } finally {
      setMutating(false);
    }
  }

  async function closeListing() {
    if (
      !selected
      || selected.publication_status
        === 'closed'
    ) {
      return;
    }

    const confirmed = window.confirm(
      (
        'Close '
        + selected.title
        + '? It will no longer be publicly available.'
      )
    );

    if (!confirmed) {
      return;
    }

    await runMutation(
      () => closeAdminInternship(
        selected.id
      ),
      selected.title + ' was closed.'
    );
  }

  async function reopenListing() {
    if (
      !selected
      || selected.publication_status
        !== 'closed'
    ) {
      return;
    }

    const confirmed = window.confirm(
      (
        'Reopen '
        + selected.title
        + '?'
      )
    );

    if (!confirmed) {
      return;
    }

    await runMutation(
      () => reopenAdminInternship(
        selected.id
      ),
      selected.title + ' was reopened.'
    );
  }

  async function deleteListing() {
    if (
      !selected
      || mutating
      || deleteMutationRef.current
    ) {
      return;
    }

    const confirmed = window.confirm(
      (
        'Permanently delete '
        + selected.title
        + '?\n\n'
        + 'Deletion is allowed only when no '
        + 'candidate has started an application. '
        + 'This action cannot be undone.'
      )
    );

    if (!confirmed) {
      return;
    }

    deleteMutationRef.current = true;
    setMutating(true);
    setPageError(null);
    setSuccess(null);

    try {
      const deletedTitle =
        selected.title;

      await deleteAdminInternship(
        selected.id
      );

      setSelected(null);
      setSelectedId(null);

      await loadListings(
        selectedStatus,
        null
      );

      setSuccess(
        deletedTitle
        + ' was permanently deleted.'
      );
    } catch (error) {
      const handled =
        await handleProtectedFailure(
          error
        );

      if (!handled) {
        setPageError(
          errorMessage(error)
        );
      }
    } finally {
      deleteMutationRef.current = false;
      setMutating(false);
    }
  }

  if (pageState === 'loading') {
    return (
      <main className="centeredState">
        <div className="stateCard">
          <span
            className="spinner"
            aria-hidden="true"
          />
          Loading internship listings...
        </div>
      </main>
    );
  }

  if (pageState === 'denied') {
    return (
      <main className="centeredState">
        <div className="stateCard">
          <h1>Access denied</h1>
          <p>
            This account does not have
            permission to use the admin
            workspace.
          </p>
          <button
            className="button buttonPrimary"
            type="button"
            onClick={() => {
              void signOut();
            }}
          >
            Return to sign in
          </button>
        </div>
      </main>
    );
  }

  async function approveListing() {
    if (
      !selected
      || selected.publication_status
        !== 'under_review'
    ) {
      return;
    }

    const confirmed = window.confirm(
      (
        'Approve and publish '
        + selected.title
        + '?'
      )
    );

    if (!confirmed) {
      return;
    }

    await runMutation(
      () => approveAdminInternship(
        selected.id
      ),
      selected.title
      + ' was approved and published.'
    );
  }


  async function requestListingChanges() {
    if (
      !selected
      || selected.publication_status
        !== 'under_review'
    ) {
      return;
    }

    const feedback =
      employerVisibleFeedback.trim();

    if (!feedback) {
      setPageError(
        'Add employer-visible feedback explaining what must be corrected.'
      );
      return;
    }

    const confirmed = window.confirm(
      (
        'Request changes for '
        + selected.title
        + '?\n\n'
        + 'The employer will see the feedback entered in the review field.'
      )
    );

    if (!confirmed) {
      return;
    }

    await runMutation(
      () => requestChangesAdminInternship(
        selected.id,
        {
          employer_visible_feedback:
            feedback,
        }
      ),
      selected.title
      + ' was returned for changes.'
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

        <details className="mobileNav">
          <summary
            className="mobileNavSummary"
            aria-label="Open administration menu"
          >
            <span
              className="mobileNavIcon"
              aria-hidden="true"
            >
              &#9776;
            </span>
            <span className="mobileNavText">
              Menu
            </span>
          </summary>

          <nav
            className="mobileNavPanel"
            aria-label="Mobile administration"
          >
            <p className="mobileNavHeading">
              Trust & Safety
            </p>

            <Link
              className="sidebarLink"
              href="/"
            >
              Organization reviews
            </Link>

            <Link
              className="sidebarLink sidebarLinkActive"
              href="/listings"
            >
              Internship listings
            </Link>

            <Link
              className="sidebarLink"
              href="/compliance"
            >
              Compliance reviews
            </Link>

            <Link
              className="sidebarLink"
              href="/users"
            >
              Users
            </Link>
            <Link
              className="sidebarLink"
              href="/promo-codes"
            >
              Promo codes
            </Link>
          </nav>
        </details>

        <nav
          className="sidebarSection"
          aria-label="Administration"
        >
          <p className="sidebarLabel">
            Trust & Safety
          </p>

          <Link
            className="sidebarLink"
            href="/"
          >
            Organization reviews
          </Link>

          <Link
            className="sidebarLink sidebarLinkActive"
            href="/listings"
          >
            Internship listings
          </Link>

          <Link
            className="sidebarLink"
            href="/compliance"
          >
            Compliance reviews
          </Link>

          <Link
            className="sidebarLink"
            href="/users"
          >
            Users
          </Link>
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
              InternMatch Admin / Listings
            </p>
            <h1>
              Internship listings
            </h1>
            <p>
              Review publication state and
              close or reopen opportunities
              when moderation requires it.
            </p>
          </div>

          <div className="topbarActions">
            <Link
              className="button buttonPrimary"
              href="/listings/new"
            >
              Create opportunity
            </Link>

            <label className="statusFilter">
              <span>Status</span>

              <select
                className="select"
                value={selectedStatus}
                disabled={
                  loadingList
                  || mutating
                }
                onChange={(event) => {
                  const value =
                    event.target.value;

                  if (
                    value !== 'all'
                    && !statuses.includes(
                      value as PublicationStatus
                    )
                  ) {
                    return;
                  }

                  const next =
                    value as StatusFilter;

                  setSelectedStatus(next);
                  setSelected(null);
                  setSelectedId(null);

                  void loadListings(
                    next,
                    null
                  );
                }}
              >
                <option value="all">
                  All statuses
                </option>

                {statuses.map(
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

            <button
              className="button buttonSecondary"
              type="button"
              disabled={
                loadingList
                || mutating
              }
              onClick={() => {
                void loadListings(
                  selectedStatus,
                  selectedId
                );
              }}
            >
              {loadingList
                ? 'Refreshing...'
                : 'Refresh'}
            </button>
          </div>
        </header>

        {pageError ? (
          <div
            className="errorBox pageMessage"
            role="alert"
          >
            {pageError}
          </div>
        ) : null}

        {success ? (
          <div
            className="successBox pageMessage"
            role="status"
          >
            {success}
          </div>
        ) : null}

        <section className="contentGrid">
          <div className="panel queuePanel">
            <div className="panelHeader">
              <div>
                <h2>
                  {selectedStatus === 'all'
                    ? 'All listings'
                    : (
                        humanize(
                          selectedStatus
                        )
                        + ' listings'
                      )}
                </h2>
                <p>
                  {totalListings}
                  {' '}
                  total
                  {' / '}
                  {listings.length}
                  {' '}
                  visible on this page
                </p>
              </div>

              <div
                className="paginationControls"
                aria-label="Internship listing pages"
              >
                <button
                  type="button"
                  className="paginationButton"
                  disabled={
                    loadingList
                    || listOffset === 0
                  }
                  onClick={() => {
                    void loadListings(
                      selectedStatus,
                      null,
                      Math.max(
                        0,
                        listOffset - 20
                      )
                    );
                  }}
                >
                  Previous
                </button>

                <span className="paginationMeta">
                  Page
                  {' '}
                  {Math.floor(listOffset / 20) + 1}
                  {' '}
                  of
                  {' '}
                  {Math.max(
                    1,
                    Math.ceil(totalListings / 20)
                  )}
                </span>

                <button
                  type="button"
                  className="paginationButton"
                  disabled={
                    loadingList
                    || (
                      listOffset
                      + listings.length
                      >= totalListings
                    )
                  }
                  onClick={() => {
                    void loadListings(
                      selectedStatus,
                      null,
                      listOffset + 20
                    );
                  }}
                >
                  Next
                </button>
              </div>
            </div>

            {listings.length === 0 ? (
              <div className="emptyState">
                <strong>
                  No listings found
                </strong>
                <span>
                  No internship listings match
                  the selected publication state.
                </span>
              </div>
            ) : (
              <div className="queueList">
                {listings.map(
                  (listing) => (
                    <button
                      key={listing.id}
                      className={
                        (
                          'queueButton'
                          + (
                            selectedId
                            === listing.id
                              ? ' queueButtonActive'
                              : ''
                          )
                        )
                      }
                      type="button"
                      disabled={mutating}
                      onClick={() => {
                        void loadDetail(
                          listing.id
                        );
                      }}
                    >
                      <span className="queueTopline">
                        <strong className="orgName">
                          {listing.title}
                        </strong>

                        <span
                          className={
                            statusClass(
                              listing
                                .publication_status
                            )
                          }
                        >
                          {
                            humanize(
                              listing
                                .publication_status
                            )
                          }
                        </span>
                      </span>

                      <span className="orgMeta">
                        {listing.company}
                      </span>

                      <span className="queueFooter">
                        <span>
                          {listing.location}
                        </span>
                        <span>
                          {humanize(
                            listing.work_type
                          )}
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
                  Listing details
                </h2>
                <p>
                  Server-authoritative
                  publication controls.
                </p>
              </div>

              {selected ? (
                <span
                  className={
                    statusClass(
                      selected
                        .publication_status
                    )
                  }
                >
                  {
                    humanize(
                      selected
                        .publication_status
                    )
                  }
                </span>
              ) : null}
            </div>

            {loadingDetail ? (
              <div className="emptyState">
                <span className="spinner" />
                <span>
                  Loading listing details...
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
                  Select a listing
                </strong>
                <span>
                  Choose an internship listing
                  to inspect it.
                </span>
              </div>
            ) : (
              <>
                <div className="detailHero">
                  <div>
                    <p className="eyebrow">
                      {selected.company}
                    </p>

                    <h3>
                      {selected.title}
                    </h3>

                    <p>
                      {selected.location}
                      {' / '}
                      {humanize(
                        selected.work_type
                      )}
                    </p>
                  </div>

                  {selected.admin_managed ? (
                    <div className="listingQuickActions">
                      <Link
                        className="button buttonSecondary"
                        href={
                          '/listings/'
                          + selected.id
                          + '/applicants'
                        }
                      >
                        Manage applicants
                      </Link>

                      <button
                        className="button buttonDanger"
                        type="button"
                        disabled={mutating}
                        onClick={() => {
                          void deleteListing();
                        }}
                      >
                        {mutating
                          ? 'Working...'
                          : 'Delete permanently'}
                      </button>
                    </div>
                  ) : null}
                </div>

                <div className="detailGrid">
                  <div className="field fieldWide">
                    <span className="label">
                      Description
                    </span>
                    <span className="value">
                      {selected.description}
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Publication status
                    </span>
                    <span className="value">
                      {
                        humanize(
                          selected
                            .publication_status
                        )
                      }
                    </span>
                  </div>

                  <div className="field">
                    <span className="label">
                      Posted
                    </span>
                    <span className="value">
                      {formatDate(
                        selected.posted_at
                      )}
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Required skills
                    </span>
                    <span className="value">
                      {
                        selected
                          .required_skills
                          .join(', ')
                        || 'None specified'
                      }
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Listing ID
                    </span>
                    <code className="codeValue">
                      {selected.id}
                    </code>
                  </div>
                </div>

                <section className="actionPanel">
                  <div className="actionPanelHeader">
                    <div>
                      <p className="eyebrow">
                        Moderation action
                      </p>
                      <h3>
                        Publication control
                      </h3>
                    </div>
                  </div>

                  {selected.publication_status === 'under_review' ? (
                    <div className="actionForm">
                      <div className="dangerNotice">
                        This employer submission is hidden from candidates
                        until an administrator approves it.
                      </div>

                      <label className="feedbackField">
                        <span className="label">
                          Employer-visible feedback
                        </span>

                        <textarea
                          className="feedbackTextarea"
                          value={employerVisibleFeedback}
                          maxLength={1000}
                          disabled={mutating}
                          placeholder={
                            'Explain exactly what the employer should correct '
                            + 'before resubmitting the listing.'
                          }
                          onChange={(event) => {
                            setEmployerVisibleFeedback(
                              event.target.value
                            );
                          }}
                        />

                        <span className="feedbackMeta">
                          This text is shown to the employer.
                          Do not include internal notes, credentials,
                          private evidence, or security-sensitive information.
                          {' '}
                          {employerVisibleFeedback.length}/1000
                        </span>
                      </label>

                      <div className="actionFooter">
                        <span className="actionHint">
                          Approval rechecks organization verification and
                          the employer plan&apos;s active-listing capacity.
                        </span>

                        <button
                          className="button buttonDanger"
                          type="button"
                          disabled={mutating}
                          onClick={() => {
                            void requestListingChanges();
                          }}
                        >
                          {mutating
                            ? 'Submitting...'
                            : 'Request changes'}
                        </button>

                        <button
                          className="button buttonPrimary"
                          type="button"
                          disabled={mutating}
                          onClick={() => {
                            void approveListing();
                          }}
                        >
                          {mutating
                            ? 'Submitting...'
                            : 'Approve & publish'}
                        </button>
                      </div>
                    </div>
                  ) : selected.publication_status === 'draft' ? (
                    <div className="actionForm">
                      <div className="dangerNotice">
                        Changes were requested or this listing is still a
                        draft. It remains hidden until the employer edits
                        and resubmits it for review.
                      </div>
                    </div>
                  ) : selected.publication_status === 'closed' ? (
                    <div className="actionForm">
                      <div className="actionFooter">
                        <span className="actionHint">
                          Employer-owned listings can reopen only when the
                          bound organization is currently verified and the
                          active-listing plan limit permits publication.
                        </span>

                        <button
                          className="button buttonPrimary"
                          type="button"
                          disabled={mutating}
                          onClick={() => {
                            void reopenListing();
                          }}
                        >
                          {mutating
                            ? 'Submitting...'
                            : 'Reopen listing'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="actionForm">
                      <div className="dangerNotice">
                        Closing removes this opportunity from public
                        discovery while preserving historical applications.
                      </div>

                      <div className="actionFooter">
                        <span className="actionHint">
                          Published here means candidate-visible under the
                          same backend visibility rule used by the app.
                        </span>

                        <button
                          className="button buttonDanger"
                          type="button"
                          disabled={mutating}
                          onClick={() => {
                            void closeListing();
                          }}
                        >
                          {mutating
                            ? 'Submitting...'
                            : 'Close listing'}
                        </button>
                      </div>
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
