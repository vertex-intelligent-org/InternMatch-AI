// ADMIN_COMPLIANCE_REVIEW_PAGE
'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  approveComplianceClaim,
  getComplianceClaimForReview,
  getComplianceEvidenceAccess,
  listComplianceClaimsForReview,
  rejectComplianceClaim,
  revokeComplianceClaim,
} from '../../lib/api';
import { getSupabaseClient } from '../../lib/supabase';
import type {
  ComplianceClaimStatus,
  EmployerComplianceClaim,
  EmployerComplianceEvidence,
} from '../../lib/types';

type PageState =
  | 'loading'
  | 'ready'
  | 'denied'
  | 'error';

type ActionMode =
  | 'approve'
  | 'reject'
  | 'revoke'
  | null;

const statuses: ComplianceClaimStatus[] = [
  'pending',
  'approved',
  'rejected',
  'revoked',
  'expired',
  'draft',
];

const metadataKeys = [
  'claim_type',
  'jurisdiction_country_code',
  'scope_key',
  'scope_label',
  'statement',
  'valid_from',
  'valid_until',
] as const;

function humanize(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => (
      character.toUpperCase()
    ));
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return 'Unexpected administration error.';
}

function statusBadgeClass(
  status: ComplianceClaimStatus
): string {
  switch (status) {
    case 'pending':
      return 'badge badgePending';
    case 'approved':
      return 'badge badgeVerified';
    case 'rejected':
    case 'revoked':
      return 'badge badgeRejected';
    default:
      return 'badge badgeNeutral';
  }
}

function fieldText(
  claim: EmployerComplianceClaim,
  key: string
): string | null {
  const value = claim[key];

  if (typeof value === 'string') {
    const cleaned = value.trim();
    return cleaned || null;
  }

  if (typeof value === 'number') {
    return String(value);
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  return null;
}

function evidenceName(
  evidence: EmployerComplianceEvidence,
  index: number
): string {
  const value = evidence.original_filename;

  if (
    typeof value === 'string'
    && value.trim()
  ) {
    return value.trim();
  }

  return `Evidence document ${index + 1}`;
}

function evidenceSize(
  evidence: EmployerComplianceEvidence
): string | null {
  const value = evidence.size_bytes;

  if (
    typeof value !== 'number'
    || !Number.isFinite(value)
    || value < 0
  ) {
    return null;
  }

  if (value < 1024) {
    return `${value} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default function AdminCompliancePage() {
  const router = useRouter();

  const [pageState, setPageState] =
    useState<PageState>('loading');

  const [adminEmail, setAdminEmail] =
    useState('');

  const [selectedStatus, setSelectedStatus] =
    useState<ComplianceClaimStatus>('pending');

  const [claims, setClaims] =
    useState<EmployerComplianceClaim[]>([]);

  const [selectedId, setSelectedId] =
    useState<string | null>(null);

  const [selected, setSelected] =
    useState<EmployerComplianceClaim | null>(null);

  const [loadingList, setLoadingList] =
    useState(false);

  const [loadingDetail, setLoadingDetail] =
    useState(false);

  const [mutating, setMutating] =
    useState(false);

  const [openingEvidenceId, setOpeningEvidenceId] =
    useState<string | null>(null);

  const [pageError, setPageError] =
    useState<string | null>(null);

  const [success, setSuccess] =
    useState<string | null>(null);

  const [actionMode, setActionMode] =
    useState<ActionMode>(null);

  const [internalNote, setInternalNote] =
    useState('');

  const [reasonCode, setReasonCode] =
    useState('');

  const resetAction = useCallback(() => {
    setActionMode(null);
    setInternalNote('');
    setReasonCode('');
  }, []);

  const handleProtectedFailure =
    useCallback(
      (error: unknown): boolean => {
        if (
          error instanceof ApiError
          && (
            error.status === 401
            || error.status === 403
          )
        ) {
          setPageState('denied');
          return true;
        }

        return false;
      },
      []
    );

  const loadDetail = useCallback(
    async (claimId: string): Promise<void> => {
      setLoadingDetail(true);

      try {
        const claim =
          await getComplianceClaimForReview(
            claimId
          );

        setSelectedId(claim.id);
        setSelected(claim);
        resetAction();
      } catch (error) {
        if (!handleProtectedFailure(error)) {
          setPageError(errorMessage(error));
        }
      } finally {
        setLoadingDetail(false);
      }
    },
    [
      handleProtectedFailure,
      resetAction,
    ]
  );

  const loadClaims = useCallback(
    async (
      statusFilter: ComplianceClaimStatus,
      preferredId: string | null
    ): Promise<void> => {
      setLoadingList(true);
      setPageError(null);

      try {
        const response =
          await listComplianceClaimsForReview(
            statusFilter
          );

        setClaims(response);
        setPageState('ready');

        const nextId =
          (
            preferredId
            && response.some(
              (claim) => claim.id === preferredId
            )
          )
            ? preferredId
            : response[0]?.id ?? null;

        if (nextId) {
          await loadDetail(nextId);
        } else {
          setSelectedId(null);
          setSelected(null);
          resetAction();
        }
      } catch (error) {
        if (!handleProtectedFailure(error)) {
          setPageState('error');
          setPageError(errorMessage(error));
        }
      } finally {
        setLoadingList(false);
      }
    },
    [
      handleProtectedFailure,
      loadDetail,
      resetAction,
    ]
  );

  useEffect(() => {
    let active = true;

    async function initialize(): Promise<void> {
      try {
        const { data, error } =
          await getSupabaseClient()
            .auth
            .getSession();

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

        await loadClaims(
          'pending',
          null
        );
      } catch (error) {
        if (!active) {
          return;
        }

        setPageState('error');
        setPageError(errorMessage(error));
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, [
    loadClaims,
    router,
  ]);

  const visibleMetadata = useMemo(
    () => (
      selected
        ? metadataKeys
            .map((key) => ({
              key,
              value: fieldText(selected, key),
            }))
            .filter(
              (
                entry
              ): entry is {
                key: typeof metadataKeys[number];
                value: string;
              } => entry.value !== null
            )
        : []
    ),
    [selected]
  );

  async function signOut(): Promise<void> {
    try {
      await getSupabaseClient()
        .auth
        .signOut();
    } finally {
      router.replace('/login');
    }
  }

  async function runMutation(
    action: () => Promise<EmployerComplianceClaim>,
    message: string
  ): Promise<void> {
    if (!selected || mutating) {
      return;
    }

    setMutating(true);
    setPageError(null);
    setSuccess(null);

    try {
      const updated = await action();

      setSuccess(message);
      resetAction();

      await loadClaims(
        selectedStatus,
        updated.id
      );
    } catch (error) {
      if (!handleProtectedFailure(error)) {
        setPageError(errorMessage(error));
      }
    } finally {
      setMutating(false);
    }
  }

  async function handleApprove(): Promise<void> {
    if (!selected) {
      return;
    }

    await runMutation(
      () => approveComplianceClaim(
        selected.id,
        {
          expected_version: selected.version,
          internal_note:
            internalNote.trim() || null,
        }
      ),
      'Compliance claim approved.'
    );
  }

  async function handleReject(): Promise<void> {
    if (!selected) {
      return;
    }

    const reason = reasonCode.trim();

    if (!reason) {
      setPageError(
        'A rejection reason code is required.'
      );
      return;
    }

    await runMutation(
      () => rejectComplianceClaim(
        selected.id,
        {
          expected_version: selected.version,
          reason_code: reason,
          internal_note:
            internalNote.trim() || null,
        }
      ),
      'Compliance claim rejected.'
    );
  }

  async function handleRevoke(): Promise<void> {
    if (!selected) {
      return;
    }

    const reason = reasonCode.trim();

    if (!reason) {
      setPageError(
        'A revocation reason code is required.'
      );
      return;
    }

    await runMutation(
      () => revokeComplianceClaim(
        selected.id,
        {
          expected_version: selected.version,
          reason_code: reason,
          internal_note:
            internalNote.trim() || null,
        }
      ),
      'Compliance approval revoked.'
    );
  }

  async function openEvidence(
    evidence: EmployerComplianceEvidence
  ): Promise<void> {
    if (!selected || openingEvidenceId) {
      return;
    }

    const popup = window.open(
      '',
      '_blank'
    );

    setOpeningEvidenceId(evidence.id);
    setPageError(null);

    try {
      const access =
        await getComplianceEvidenceAccess(
          selected.id,
          evidence.id
        );

      if (popup) {
        popup.location.href =
          access.evidence_url;
      } else {
        window.location.href =
          access.evidence_url;
      }
    } catch (error) {
      if (popup) {
        popup.close();
      }

      if (!handleProtectedFailure(error)) {
        setPageError(errorMessage(error));
      }
    } finally {
      setOpeningEvidenceId(null);
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
          Loading compliance review queue...
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
            permission to review employer
            compliance evidence.
          </p>
          <button
            className="button buttonSecondary"
            type="button"
            onClick={() => {
              void signOut();
            }}
          >
            Sign out
          </button>
        </div>
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
              className="sidebarLink"
              href="/listings"
            >
              Internship listings
            </Link>

            <Link
              className="sidebarLink sidebarLinkActive"
              href="/compliance"
            >
              Compliance reviews
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
            className="sidebarLink"
            href="/listings"
          >
            Internship listings
          </Link>

          <Link
            className="sidebarLink sidebarLinkActive"
            href="/compliance"
          >
            Compliance reviews
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
              InternMatch Admin / Compliance
            </p>
            <h1>
              Employer compliance reviews
            </h1>
            <p>
              Review jurisdiction-scoped
              compliance claims and their
              private supporting evidence.
              Organization identity verification
              remains a separate authority.
            </p>
          </div>

          <div className="topbarActions">
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
                  const next = event.target.value as ComplianceClaimStatus;

                  setSelectedStatus(next);
                  setSelectedId(null);
                  setSelected(null);
                  resetAction();

                  void loadClaims(
                    next,
                    null
                  );
                }}
              >
                {statuses.map((status) => (
                  <option
                    key={status}
                    value={status}
                  >
                    {humanize(status)}
                  </option>
                ))}
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
                void loadClaims(
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
                  {humanize(selectedStatus)}
                  {' '}
                  claims
                </h2>
                <p>
                  {claims.length}
                  {' '}
                  visible in this queue
                </p>
              </div>
            </div>

            {claims.length === 0 ? (
              <div className="emptyState">
                <strong>
                  No compliance claims found
                </strong>
                <span>
                  No claims match the selected
                  review state.
                </span>
              </div>
            ) : (
              <div className="queueList">
                {claims.map((claim) => {
                  const kind =
                    fieldText(
                      claim,
                      'claim_type'
                    )
                    ?? fieldText(
                      claim,
                      'compliance_type'
                    )
                    ?? fieldText(
                      claim,
                      'requirement_type'
                    )
                    ?? fieldText(
                      claim,
                      'document_type'
                    )
                    ?? 'Compliance claim';

                  const country =
                    fieldText(
                      claim,
                      'jurisdiction_country_code'
                    );

                  return (
                    <button
                      key={claim.id}
                      className={
                        (
                          'queueButton'
                          + (
                            selectedId
                            === claim.id
                              ? ' queueButtonActive'
                              : ''
                          )
                        )
                      }
                      type="button"
                      disabled={mutating}
                      onClick={() => {
                        setSuccess(null);
                        setPageError(null);
                        void loadDetail(
                          claim.id
                        );
                      }}
                    >
                      <div className="queueRow">
                        <strong>{kind}</strong>
                        <span
                          className={
                            statusBadgeClass(
                              claim.status
                            )
                          }
                        >
                          {humanize(
                            claim.status
                          )}
                        </span>
                      </div>

                      <span>
                        {country
                          ? `Jurisdiction: ${country}`
                          : 'Jurisdiction-scoped claim'}
                      </span>

                      <small>
                        Version {claim.version}
                      </small>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="panel detailPanel">
            <div className="panelHeader">
              <div>
                <h2>
                  Compliance claim details
                </h2>
                <p>
                  Server-authoritative review
                  state and private evidence
                  access.
                </p>
              </div>

              {selected ? (
                <span
                  className={
                    statusBadgeClass(
                      selected.status
                    )
                  }
                >
                  {humanize(
                    selected.status
                  )}
                </span>
              ) : null}
            </div>

            {loadingDetail ? (
              <div className="emptyState">
                <span
                  className="spinner"
                  aria-hidden="true"
                />
                Loading claim details...
              </div>
            ) : !selected ? (
              <div className="emptyState">
                <strong>
                  Select a compliance claim
                </strong>
                <span>
                  Choose an item from the review
                  queue to inspect it.
                </span>
              </div>
            ) : (
              <>
                <div className="detailGrid">
                  {visibleMetadata.map(
                    ({ key, value }) => (
                      <div
                        className="field"
                        key={key}
                      >
                        <span className="label">
                          {humanize(key)}
                        </span>
                        <span className="value">
                          {value}
                        </span>
                      </div>
                    )
                  )}

                  <div className="field">
                    <span className="label">
                      Version
                    </span>
                    <span className="value">
                      {selected.version}
                    </span>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Organization ID
                    </span>
                    <code className="codeValue">
                      {selected.organization_id}
                    </code>
                  </div>

                  <div className="field fieldWide">
                    <span className="label">
                      Claim ID
                    </span>
                    <code className="codeValue">
                      {selected.id}
                    </code>
                  </div>

                  {selected.rejection_reason_code ? (
                    <div className="field fieldWide">
                      <span className="label">
                        Review reason
                      </span>
                      <span className="value">
                        {humanize(
                          selected
                            .rejection_reason_code
                        )}
                      </span>
                    </div>
                  ) : null}
                </div>

                <section className="actionPanel">
                  <div className="actionPanelHeader">
                    <div>
                      <p className="eyebrow">
                        Private evidence
                      </p>
                      <h3>
                        Supporting documents
                      </h3>
                    </div>
                  </div>

                  {(
                    selected.evidence
                    ?? []
                  ).length === 0 ? (
                    <div className="readOnlyNotice">
                      No supporting evidence is
                      attached to this claim.
                    </div>
                  ) : (
                    <div className="queueList">
                      {(
                        selected.evidence
                        ?? []
                      ).map(
                        (
                          evidence,
                          index
                        ) => (
                          <div
                            className="queueButton"
                            key={evidence.id}
                          >
                            <div className="queueRow">
                              <strong>
                                {evidenceName(
                                  evidence,
                                  index
                                )}
                              </strong>
                              {evidenceSize(
                                evidence
                              ) ? (
                                <span>
                                  {evidenceSize(
                                    evidence
                                  )}
                                </span>
                              ) : null}
                            </div>

                            <button
                              className="button buttonSecondary"
                              type="button"
                              disabled={
                                openingEvidenceId
                                !== null
                              }
                              onClick={() => {
                                void openEvidence(
                                  evidence
                                );
                              }}
                            >
                              {openingEvidenceId
                                === evidence.id
                                ? 'Opening...'
                                : 'Open secure document'}
                            </button>
                          </div>
                        )
                      )}
                    </div>
                  )}
                </section>

                <section className="actionPanel">
                  <div className="actionPanelHeader">
                    <div>
                      <p className="eyebrow">
                        Review action
                      </p>
                      <h3>
                        Compliance decision
                      </h3>
                    </div>
                  </div>

                  {selected.status
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
                          disabled={mutating}
                          onClick={() => {
                            setActionMode(
                              'approve'
                            );
                            setPageError(null);
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
                          disabled={mutating}
                          onClick={() => {
                            setActionMode(
                              'reject'
                            );
                            setPageError(null);
                          }}
                        >
                          Reject
                        </button>
                      </div>

                      {actionMode
                        === 'approve' ? (
                        <div className="actionForm">
                          <label className="formField">
                            <span>
                              Internal review note
                            </span>
                            <textarea
                              className="input textarea"
                              maxLength={2000}
                              value={internalNote}
                              disabled={mutating}
                              placeholder="Optional internal compliance review context."
                              onChange={(event) => {
                                setInternalNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              Reviewer identity and
                              review time are assigned
                              by the backend.
                            </span>

                            <button
                              className="button buttonPrimary"
                              type="button"
                              disabled={mutating}
                              onClick={() => {
                                void handleApprove();
                              }}
                            >
                              {mutating
                                ? 'Submitting...'
                                : 'Approve compliance claim'}
                            </button>
                          </div>
                        </div>
                      ) : null}

                      {actionMode
                        === 'reject' ? (
                        <div className="actionForm">
                          <label className="formField">
                            <span>
                              Rejection reason code
                            </span>
                            <input
                              className="input"
                              maxLength={100}
                              value={reasonCode}
                              disabled={mutating}
                              placeholder="insufficient_evidence"
                              onChange={(event) => {
                                setReasonCode(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <label className="formField">
                            <span>
                              Internal review note
                            </span>
                            <textarea
                              className="input textarea"
                              maxLength={2000}
                              value={internalNote}
                              disabled={mutating}
                              placeholder="Optional internal compliance review context."
                              onChange={(event) => {
                                setInternalNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              The employer may correct
                              the claim and submit it
                              again where permitted.
                            </span>

                            <button
                              className="button buttonDanger"
                              type="button"
                              disabled={mutating}
                              onClick={() => {
                                void handleReject();
                              }}
                            >
                              {mutating
                                ? 'Submitting...'
                                : 'Reject compliance claim'}
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : selected.status
                    === 'approved' ? (
                    <>
                      <div className="actionTabs">
                        <button
                          className={
                            (
                              'button '
                              + (
                                actionMode
                                === 'revoke'
                                  ? 'buttonDanger'
                                  : 'buttonSecondary'
                              )
                            )
                          }
                          type="button"
                          disabled={mutating}
                          onClick={() => {
                            setActionMode(
                              'revoke'
                            );
                            setPageError(null);
                          }}
                        >
                          Revoke approval
                        </button>
                      </div>

                      {actionMode
                        === 'revoke' ? (
                        <div className="actionForm">
                          <label className="formField">
                            <span>
                              Revocation reason code
                            </span>
                            <input
                              className="input"
                              maxLength={100}
                              value={reasonCode}
                              disabled={mutating}
                              placeholder="evidence_no_longer_valid"
                              onChange={(event) => {
                                setReasonCode(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <label className="formField">
                            <span>
                              Internal review note
                            </span>
                            <textarea
                              className="input textarea"
                              maxLength={2000}
                              value={internalNote}
                              disabled={mutating}
                              placeholder="Optional internal compliance review context."
                              onChange={(event) => {
                                setInternalNote(
                                  event.target.value
                                );
                              }}
                            />
                          </label>

                          <div className="actionFooter">
                            <span className="actionHint">
                              Revocation is
                              server-authoritative and
                              version checked.
                            </span>

                            <button
                              className="button buttonDanger"
                              type="button"
                              disabled={mutating}
                              onClick={() => {
                                void handleRevoke();
                              }}
                            >
                              {mutating
                                ? 'Submitting...'
                                : 'Revoke approval'}
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="readOnlyNotice">
                      No moderation action is
                      available for this claim state.
                      You can still inspect the claim
                      and its authorized evidence.
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
