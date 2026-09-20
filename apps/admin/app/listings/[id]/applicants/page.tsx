'use client';

// ADMIN_APPLICANTS_WORKSPACE

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import Link from 'next/link';
import {
  useParams,
  useRouter,
} from 'next/navigation';

import {
  ApiError,
  downloadAdminInternshipApplicantCV,
  getAdminInternship,
  listAdminInternshipApplicants,
  scheduleAdminInternshipApplicantInterview,
  updateAdminInternshipApplicantStatus,
} from '../../../../lib/api';

import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../../../../lib/supabase';

import type {
  AdminApplicantItem,
  AdminApplicationStatus,
  AdminInternshipDetail,
} from '../../../../lib/types';

type PageState =
  | 'loading'
  | 'ready'
  | 'error';

function humanize(
  value: string
): string {
  return value
    .split('_')
    .map(
      (part) =>
        part.charAt(0).toUpperCase()
        + part.slice(1)
    )
    .join(' ');
}

function formatDate(
  value: string | null
): string {
  if (!value) {
    return 'Not available';
  }

  const parsed = new Date(value);

  if (
    Number.isNaN(
      parsed.getTime()
    )
  ) {
    return value;
  }

  return parsed.toLocaleString();
}

function statusClass(
  status: AdminApplicationStatus
): string {
  switch (status) {
    case 'accepted':
      return 'badge badgeVerified';

    case 'rejected':
      return 'badge badgeSuspended';

    case 'interviewing':
      return 'badge badgePending';

    default:
      return 'badge badgeNeutral';
  }
}

function errorMessage(
  error: unknown
): string {
  if (
    error
    instanceof AdminConfigurationError
  ) {
    return (
      'The admin workspace is not fully '
      + 'configured on this device yet.'
    );
  }

  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Unable to complete the request.';
}

export default function AdminApplicantsPage() {
  const router = useRouter();

  const params = useParams<{
    id: string;
  }>();

  const internshipId =
    typeof params.id === 'string'
      ? params.id
      : '';

  const mutationRef = useRef(false);

  const [pageState, setPageState] =
    useState<PageState>('loading');

  const [listing, setListing] =
    useState<
      AdminInternshipDetail | null
    >(null);

  const [applicants, setApplicants] =
    useState<AdminApplicantItem[]>([]);

  const [error, setError] =
    useState<string | null>(null);

  const [success, setSuccess] =
    useState<string | null>(null);

  const [
    mutatingId,
    setMutatingId,
  ] = useState<string | null>(null);

  const [
    openingCvId,
    setOpeningCvId,
  ] = useState<string | null>(null);

  const [
    interviewApplicationId,
    setInterviewApplicationId,
  ] = useState<string | null>(null);

  const [
    interviewDateTime,
    setInterviewDateTime,
  ] = useState('');

  const [
    interviewMode,
    setInterviewMode,
  ] = useState<
    'online' | 'onsite'
  >('online');

  const [
    interviewLocation,
    setInterviewLocation,
  ] = useState('');

  const [
    interviewMessage,
    setInterviewMessage,
  ] = useState('');

  const handleProtectedFailure =
    useCallback(
      async (
        apiError: unknown
      ): Promise<boolean> => {
        if (
          !(apiError instanceof ApiError)
        ) {
          return false;
        }

        if (
          apiError.status !== 401
          && apiError.status !== 403
        ) {
          return false;
        }

        try {
          await getSupabaseClient()
            .auth
            .signOut();
        } finally {
          router.replace('/login');
        }

        return true;
      },
      [router]
    );

  const loadApplicants =
    useCallback(
      async (): Promise<void> => {
        if (!internshipId) {
          setPageState('error');
          setError(
            'Internship reference is missing.'
          );
          return;
        }

        setError(null);

        try {
          const [
            listingResponse,
            applicantResponse,
          ] = await Promise.all([
            getAdminInternship(
              internshipId
            ),
            listAdminInternshipApplicants(
              internshipId
            ),
          ]);

          setListing(
            listingResponse
          );

          setApplicants(
            applicantResponse.items
          );

          setPageState('ready');
        } catch (loadError) {
          const handled =
            await handleProtectedFailure(
              loadError
            );

          if (!handled) {
            setError(
              errorMessage(loadError)
            );
            setPageState('error');
          }
        }
      },
      [
        handleProtectedFailure,
        internshipId,
      ]
    );

  useEffect(() => {
    let active = true;

    async function initialize() {
      try {
        const {
          data,
          error: sessionError,
        } =
          await getSupabaseClient()
            .auth
            .getSession();

        if (!active) {
          return;
        }

        if (
          sessionError
          || !data.session
        ) {
          router.replace('/login');
          return;
        }

        await loadApplicants();
      } catch (initializeError) {
        if (!active) {
          return;
        }

        setError(
          errorMessage(
            initializeError
          )
        );

        setPageState('error');
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, [
    loadApplicants,
    router,
  ]);

  function replaceApplicant(
    updated: AdminApplicantItem
  ) {
    setApplicants(
      (current) =>
        current.map(
          (item) =>
            item.application_id
            === updated.application_id
              ? updated
              : item
        )
    );
  }


  async function openCandidateCv(
    applicant: AdminApplicantItem
  ): Promise<void> {
    if (openingCvId !== null) {
      return;
    }

    // Open synchronously from the user's click so
    // browser popup protection does not turn the
    // secure document flow into a downloadable URL.
    const popup = window.open(
      '',
      '_blank'
    );

    if (popup) {
      try {
        popup.opener = null;
        popup.document.title =
          'Opening secure candidate CV...';
      } catch {
        // The document access flow does not rely
        // on manipulating the popup document.
      }
    }

    setOpeningCvId(
      applicant.application_id
    );

    setError(null);

    let objectUrl: string | null =
      null;

    try {
      const blob =
        await downloadAdminInternshipApplicantCV(
          internshipId,
          applicant.application_id
        );

      objectUrl =
        URL.createObjectURL(blob);

      if (popup) {
        popup.location.replace(
          objectUrl
        );
      } else {
        window.open(
          objectUrl,
          '_blank',
          'noopener,noreferrer'
        );
      }

      const disposableUrl =
        objectUrl;

      // The Blob URL is browser-local and temporary.
      // No storage-provider URL exists in the client.
      window.setTimeout(
        () => {
          URL.revokeObjectURL(
            disposableUrl
          );
        },
        60_000
      );
    } catch (cvError) {
      if (popup) {
        popup.close();
      }

      const handled =
        await handleProtectedFailure(
          cvError
        );

      if (!handled) {
        setError(
          cvError instanceof ApiError
          && (
            cvError.status === 403
            || cvError.status === 404
          )
            ? (
                'This CV is unavailable or '
                + 'you do not have permission '
                + 'to access it.'
              )
            : errorMessage(cvError)
        );
      }
    } finally {
      setOpeningCvId(null);
    }
  }

  async function updateStatus(
    applicant: AdminApplicantItem,
    target:
      | 'accepted'
      | 'rejected'
  ) {
    if (
      mutationRef.current
      || applicant.status === 'accepted'
      || applicant.status === 'rejected'
    ) {
      return;
    }

    const confirmed =
      window.confirm(
        target === 'accepted'
          ? (
              'Accept '
              + applicant
                .candidate
                .full_name
              + '? The candidate will see '
              + 'the updated status.'
            )
          : (
              'Reject '
              + applicant
                .candidate
                .full_name
              + '? This application '
              + 'will become terminal.'
            )
      );

    if (!confirmed) {
      return;
    }

    mutationRef.current = true;

    setMutatingId(
      applicant.application_id
    );

    setError(null);
    setSuccess(null);

    try {
      const updated =
        await updateAdminInternshipApplicantStatus(
          internshipId,
          applicant.application_id,
          {
            status: target,
          }
        );

      replaceApplicant(updated);

      setSuccess(
        applicant.candidate.full_name
        + ' was marked '
        + target
        + '.'
      );
    } catch (mutationError) {
      const handled =
        await handleProtectedFailure(
          mutationError
        );

      if (!handled) {
        setError(
          errorMessage(
            mutationError
          )
        );
      }
    } finally {
      mutationRef.current = false;
      setMutatingId(null);
    }
  }

  function openInterview(
    applicant: AdminApplicantItem
  ) {
    setInterviewApplicationId(
      applicant.application_id
    );

    setInterviewMode(
      applicant.interview_mode
      ?? 'online'
    );

    setInterviewLocation(
      applicant.interview_location
      ?? ''
    );

    setInterviewMessage(
      applicant.interview_message
      ?? ''
    );

    if (
      applicant.interview_scheduled_at
    ) {
      const parsed = new Date(
        applicant.interview_scheduled_at
      );

      if (
        !Number.isNaN(
          parsed.getTime()
        )
      ) {
        const local =
          new Date(
            parsed.getTime()
            - parsed.getTimezoneOffset()
              * 60000
          )
            .toISOString()
            .slice(0, 16);

        setInterviewDateTime(
          local
        );
        return;
      }
    }

    setInterviewDateTime('');
  }

  async function scheduleInterview(
    applicant: AdminApplicantItem
  ) {
    if (mutationRef.current) {
      return;
    }

    if (
      !interviewDateTime.trim()
      || !interviewLocation.trim()
    ) {
      setError(
        'Interview date, time, and '
        + 'location are required.'
      );
      return;
    }

    const scheduled = new Date(
      interviewDateTime
    );

    if (
      Number.isNaN(
        scheduled.getTime()
      )
    ) {
      setError(
        'Enter a valid interview date and time.'
      );
      return;
    }

    if (
      scheduled.getTime()
      <= Date.now()
    ) {
      setError(
        'Interview must be scheduled '
        + 'in the future.'
      );
      return;
    }

    mutationRef.current = true;

    setMutatingId(
      applicant.application_id
    );

    setError(null);
    setSuccess(null);

    try {
      const updated =
        await scheduleAdminInternshipApplicantInterview(
          internshipId,
          applicant.application_id,
          {
            scheduled_at:
              scheduled.toISOString(),
            mode:
              interviewMode,
            location:
              interviewLocation.trim(),
            message:
              interviewMessage.trim()
              || null,
          }
        );

      replaceApplicant(updated);

      setInterviewApplicationId(
        null
      );

      setSuccess(
        'Interview scheduled for '
        + applicant.candidate.full_name
        + '.'
      );
    } catch (mutationError) {
      const handled =
        await handleProtectedFailure(
          mutationError
        );

      if (!handled) {
        setError(
          errorMessage(
            mutationError
          )
        );
      }
    } finally {
      mutationRef.current = false;
      setMutatingId(null);
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
          Loading applicants...
        </div>
      </main>
    );
  }

  return (
    <main className="adminApplicantsPage">
      <header className="topbar">
        <div>
          <p className="eyebrow">
            InternMatch Admin / Applicants
          </p>

          <h1>
            {
              listing?.title
              ?? 'Applicants'
            }
          </h1>

          <p>
            {
              listing
                ? (
                    listing.company
                    + ' / '
                    + listing.location
                  )
                : 'Manage submitted applications.'
            }
          </p>
        </div>

        <div className="topbarActions">
          <Link
            className="button buttonSecondary"
            href="/listings"
          >
            Back to listings
          </Link>

          <button
            className="button buttonSecondary"
            type="button"
            disabled={
              mutationRef.current
            }
            onClick={() => {
              void loadApplicants();
            }}
          >
            Refresh
          </button>
        </div>
      </header>

      {error ? (
        <div
          className="errorBox pageMessage"
          role="alert"
        >
          {error}
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

      {pageState === 'error' ? (
        <section className="panel">
          <div className="emptyState">
            <strong>
              Applicants unavailable
            </strong>
            <span>
              {error ?? 'Unable to load applicants.'}
            </span>
          </div>
        </section>
      ) : applicants.length === 0 ? (
        <section className="panel">
          <div className="emptyState">
            <strong>
              No submitted applicants yet
            </strong>
            <span>
              Saved candidate drafts stay private
              and do not appear here.
            </span>
          </div>
        </section>
      ) : (
        <section className="adminApplicantsGrid">
          {applicants.map(
            (applicant) => {
              const terminal =
                applicant.status === 'accepted'
                || applicant.status === 'rejected';

              const busy =
                mutatingId
                === applicant.application_id;

              const interviewOpen =
                interviewApplicationId
                === applicant.application_id;

              return (
                <article
                  className="panel adminApplicantCard"
                  key={applicant.application_id}
                >
                  <div className="panelHeader">
                    <div>
                      <h2>
                        {applicant.candidate.full_name}
                      </h2>
                      <p>
                        {
                          applicant.candidate.department
                          ?? 'Department not provided'
                        }
                      </p>
                    </div>

                    <span
                      className={
                        statusClass(
                          applicant.status
                        )
                      }
                    >
                      {humanize(applicant.status)}
                    </span>
                  </div>

                  <div className="adminApplicantBody">
                    <div className="detailGrid adminApplicantDetailGrid">
                      <div className="field">
                        <span className="label">
                          Applied
                        </span>
                        <span className="value">
                          {
                            formatDate(
                              applicant.applied_date
                            )
                          }
                        </span>
                      </div>

                      <div className="field">
                        <span className="label">
                          Status
                        </span>
                        <span className="value">
                          {humanize(applicant.status)}
                        </span>
                      </div>

                      <div className="field fieldWide">
                        <span className="label">
                          Candidate skills
                        </span>
                        <span className="value">
                          {
                            applicant
                              .candidate
                              .skills
                              .join(', ')
                            || 'None listed'
                          }
                        </span>
                      </div>

                      <div className="field fieldWide">
                        <span className="label">
                          Cover letter
                        </span>
                        <span className="value adminCoverLetter">
                          {
                            applicant
                              .generated_cover_letter
                            || 'No cover letter available.'
                          }
                        </span>
                      </div>

                      <div className="field fieldWide">
                        <span className="label">
                          Candidate CV
                        </span>

                        <div className="value">
                          <button
                            className="button buttonSecondary"
                            type="button"
                            disabled={
                              openingCvId !== null
                            }
                            onClick={() => {
                              void openCandidateCv(
                                applicant
                              );
                            }}
                          >
                            {
                              openingCvId
                              === applicant.application_id
                                ? 'Opening securely...'
                                : 'Open CV securely'
                            }
                          </button>
                        </div>
                      </div>

                      {
                        applicant
                          .interview_scheduled_at
                          ? (
                            <div className="field fieldWide">
                              <span className="label">
                                Interview
                              </span>
                              <span className="value">
                                {
                                  formatDate(
                                    applicant
                                      .interview_scheduled_at
                                  )
                                }
                                {' / '}
                                {
                                  humanize(
                                    applicant
                                      .interview_mode
                                    ?? 'online'
                                  )
                                }
                                {' / '}
                                {
                                  applicant
                                    .interview_location
                                }
                              </span>
                            </div>
                          )
                          : null
                      }
                    </div>

                    {!terminal ? (
                      <div className="adminApplicantActions">
                        <button
                          className="button buttonSecondary"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            openInterview(
                              applicant
                            );
                          }}
                        >
                          Interview
                        </button>

                        <button
                          className="button buttonPrimary"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            void updateStatus(
                              applicant,
                              'accepted'
                            );
                          }}
                        >
                          Accept
                        </button>

                        <button
                          className="button buttonDanger"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            void updateStatus(
                              applicant,
                              'rejected'
                            );
                          }}
                        >
                          Reject
                        </button>
                      </div>
                    ) : null}

                    {
                      interviewOpen && !terminal
                        ? (
                          <div className="adminInterviewForm">
                            <label className="formField">
                              <span>
                                Date and time
                              </span>
                              <input
                                className="input"
                                type="datetime-local"
                                value={interviewDateTime}
                                disabled={busy}
                                onChange={(event) => {
                                  setInterviewDateTime(
                                    event.target.value
                                  );
                                }}
                              />
                            </label>

                            <label className="formField">
                              <span>
                                Mode
                              </span>
                              <select
                                className="select"
                                value={interviewMode}
                                disabled={busy}
                                onChange={(event) => {
                                  const value =
                                    event.target.value;

                                  if (
                                    value === 'online'
                                    || value === 'onsite'
                                  ) {
                                    setInterviewMode(
                                      value
                                    );
                                  }
                                }}
                              >
                                <option value="online">
                                  Online
                                </option>
                                <option value="onsite">
                                  On-site
                                </option>
                              </select>
                            </label>

                            <label className="formField adminInterviewWide">
                              <span>
                                Meeting link or location
                              </span>
                              <input
                                className="input"
                                value={interviewLocation}
                                maxLength={500}
                                disabled={busy}
                                onChange={(event) => {
                                  setInterviewLocation(
                                    event.target.value
                                  );
                                }}
                              />
                            </label>

                            <label className="formField adminInterviewWide">
                              <span>
                                Message
                              </span>
                              <textarea
                                className="input textarea"
                                value={interviewMessage}
                                maxLength={2000}
                                disabled={busy}
                                onChange={(event) => {
                                  setInterviewMessage(
                                    event.target.value
                                  );
                                }}
                              />
                            </label>

                            <div className="adminInterviewActions adminInterviewWide">
                              <button
                                className="button buttonSecondary"
                                type="button"
                                disabled={busy}
                                onClick={() => {
                                  setInterviewApplicationId(
                                    null
                                  );
                                }}
                              >
                                Cancel
                              </button>

                              <button
                                className="button buttonPrimary"
                                type="button"
                                disabled={busy}
                                onClick={() => {
                                  void scheduleInterview(
                                    applicant
                                  );
                                }}
                              >
                                {
                                  busy
                                    ? 'Scheduling...'
                                    : 'Schedule interview'
                                }
                              </button>
                            </div>
                          </div>
                        )
                        : null
                    }
                  </div>
                </article>
              );
            }
          )}
        </section>
      )}
    </main>
  );
}
