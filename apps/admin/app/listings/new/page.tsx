'use client';

import {
  useEffect,
  useRef,
  useState,
} from 'react';
import type {
  FormEvent,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  createAdminInternship,
} from '../../../lib/api';
import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../../../lib/supabase';
import type {
  AdminInternshipCreatePayload,
} from '../../../lib/types';

type PageState =
  | 'loading'
  | 'ready'
  | 'error';

type WorkType =
  AdminInternshipCreatePayload['work_type'];

type PublicationChoice =
  AdminInternshipCreatePayload[
    'publication_status'
  ];

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

  return 'Unable to create the opportunity.';
}

function parseSkills(
  value: string
): string[] {
  return Array.from(
    new Set(
      value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
}

function nullable(
  value: string
): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export default function CreateOpportunityPage() {
  const router = useRouter();

  const submitInFlightRef =
    useRef(false);

  const [pageState, setPageState] =
    useState<PageState>('loading');

  const [adminEmail, setAdminEmail] =
    useState('');

  const [submitting, setSubmitting] =
    useState(false);

  const [pageError, setPageError] =
    useState<string | null>(null);

  const [title, setTitle] =
    useState('');

  const [company, setCompany] =
    useState('InternMatch AI Team');

  const [location, setLocation] =
    useState('');

  const [workType, setWorkType] =
    useState<WorkType>('remote');

  const [description, setDescription] =
    useState('');

  const [requiredSkills, setRequiredSkills] =
    useState('');

  const [preferredSkills, setPreferredSkills] =
    useState('');

  const [language, setLanguage] =
    useState('English');

  const [
    educationRequirements,
    setEducationRequirements,
  ] = useState('');

  const [
    experienceRequirements,
    setExperienceRequirements,
  ] = useState('');

  const [
    publicationStatus,
    setPublicationStatus,
  ] = useState<PublicationChoice>(
    'published'
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

        if (
          error
          || !data.session
        ) {
          router.replace('/login');
          return;
        }

        setAdminEmail(
          data.session.user.email
          ?? 'Authorized administrator'
        );

        setPageState('ready');
      } catch (error) {
        if (!active) {
          return;
        }

        setPageError(
          errorMessage(error)
        );
        setPageState('error');
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

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (
      submitInFlightRef.current
      || submitting
    ) {
      return;
    }

    const normalizedCompany =
      company.trim();

    if (!normalizedCompany) {
      setPageError(
        'Company / organization name is required.'
      );
      return;
    }

    if (
      publicationStatus === 'published'
    ) {
      const confirmed = window.confirm(
        (
          'Publish this opportunity now? '
          + 'It will become visible to candidates immediately.'
        )
      );

      if (!confirmed) {
        return;
      }
    }

    submitInFlightRef.current = true;
    setSubmitting(true);
    setPageError(null);

    const payload:
      AdminInternshipCreatePayload = {
        title: title.trim(),
        company: normalizedCompany,
        location: location.trim(),
        work_type: workType,
        description: description.trim(),
        required_skills:
          parseSkills(requiredSkills),
        preferred_skills:
          parseSkills(preferredSkills),
        language:
          nullable(language),
        education_requirements:
          nullable(educationRequirements),
        experience_requirements:
          nullable(experienceRequirements),
        publication_status:
          publicationStatus,
      };

    try {
      await createAdminInternship(
        payload
      );

      router.push('/listings');
    } catch (error) {
      if (
        error instanceof ApiError
        && (
          error.status === 401
          || error.status === 403
        )
      ) {
        try {
          await getSupabaseClient()
            .auth
            .signOut();
        } finally {
          router.replace('/login');
        }
        return;
      }

      setPageError(
        errorMessage(error)
      );
    } finally {
      submitInFlightRef.current = false;
      setSubmitting(false);
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
          Loading admin workspace...
        </div>
      </main>
    );
  }

  if (pageState === 'error') {
    return (
      <main className="centeredState">
        <div className="stateCard">
          <h1>Unable to open creator</h1>
          <p>
            {pageError}
          </p>
          <Link
            className="button buttonSecondary"
            href="/listings"
          >
            Back to listings
          </Link>
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
            className={
              'sidebarLink '
              + 'sidebarLinkActive'
            }
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
              <strong>
                Administrator
              </strong>
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
              Create opportunity
            </h1>
            <p>
              Publish a first-party or
              administrator-curated opportunity
              using the same canonical fields
              candidates see in the app.
            </p>
          </div>

          <div className="topbarActions">
            <Link
              className="button buttonSecondary"
              href="/listings"
            >
              Back to listings
            </Link>
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

        <section
          className={
            'panel createListingPanel'
          }
        >
          <div className="panelHeader">
            <div>
              <h2>
                Opportunity details
              </h2>
              <p>
                Admin-created listings are
                internally recorded as curated,
                never employer-authored.
              </p>
            </div>
          </div>

          <form
            className="createListingForm"
            onSubmit={(event) => {
              void handleSubmit(event);
            }}
          >
            <div className="createListingGrid">
              <label className="formField">
                <span>Opportunity title</span>
                <input
                  className="input"
                  value={title}
                  maxLength={200}
                  required
                  disabled={submitting}
                  onChange={(event) => {
                    setTitle(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'e.g. AI Software Engineer Intern'
                  }
                />
              </label>

              <label className="formField">
                <span>
                  Company / organization
                </span>
                <input
                  className="input"
                  value={company}
                  maxLength={200}
                  required
                  disabled={submitting}
                  onChange={(event) => {
                    setCompany(
                      event.target.value
                    );
                  }}
                />
                <small className="formHelper">
                  Use a real organization name
                  only when you are authorized
                  to publish for it.
                </small>
              </label>

              <label className="formField">
                <span>Location</span>
                <input
                  className="input"
                  value={location}
                  maxLength={200}
                  required
                  disabled={submitting}
                  onChange={(event) => {
                    setLocation(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Istanbul, Turkiye or Remote'
                  }
                />
              </label>

              <label className="formField">
                <span>Work type</span>
                <select
                  className="input"
                  value={workType}
                  disabled={submitting}
                  onChange={(event) => {
                    setWorkType(
                      event.target
                        .value as WorkType
                    );
                  }}
                >
                  <option value="remote">
                    Remote
                  </option>
                  <option value="hybrid">
                    Hybrid
                  </option>
                  <option value="onsite">
                    On-site
                  </option>
                </select>
              </label>

              <label
                className={
                  'formField '
                  + 'createListingWide'
                }
              >
                <span>Description</span>
                <textarea
                  className="input textarea"
                  value={description}
                  required
                  disabled={submitting}
                  onChange={(event) => {
                    setDescription(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Describe the role, responsibilities, and opportunity.'
                  }
                />
              </label>

              <label className="formField">
                <span>
                  Required skills
                </span>
                <input
                  className="input"
                  value={requiredSkills}
                  disabled={submitting}
                  onChange={(event) => {
                    setRequiredSkills(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Python, FastAPI, PostgreSQL'
                  }
                />
                <small className="formHelper">
                  Separate skills with commas.
                </small>
              </label>

              <label className="formField">
                <span>
                  Preferred skills
                </span>
                <input
                  className="input"
                  value={preferredSkills}
                  disabled={submitting}
                  onChange={(event) => {
                    setPreferredSkills(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Docker, Redis, AWS'
                  }
                />
                <small className="formHelper">
                  Separate skills with commas.
                </small>
              </label>

              <label className="formField">
                <span>Language</span>
                <input
                  className="input"
                  value={language}
                  disabled={submitting}
                  onChange={(event) => {
                    setLanguage(
                      event.target.value
                    );
                  }}
                />
              </label>

              <label className="formField">
                <span>
                  Publication
                </span>
                <select
                  className="input"
                  value={publicationStatus}
                  disabled={submitting}
                  onChange={(event) => {
                    setPublicationStatus(
                      event.target
                        .value as PublicationChoice
                    );
                  }}
                >
                  <option value="published">
                    Publish now
                  </option>
                  <option value="draft">
                    Save as draft
                  </option>
                </select>
                <small className="formHelper">
                  Published opportunities become
                  visible to candidates immediately.
                </small>
              </label>

              <label
                className={
                  'formField '
                  + 'createListingWide'
                }
              >
                <span>
                  Education requirements
                </span>
                <textarea
                  className="input textarea"
                  value={educationRequirements}
                  disabled={submitting}
                  onChange={(event) => {
                    setEducationRequirements(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Optional education requirements'
                  }
                />
              </label>

              <label
                className={
                  'formField '
                  + 'createListingWide'
                }
              >
                <span>
                  Experience requirements
                </span>
                <textarea
                  className="input textarea"
                  value={experienceRequirements}
                  disabled={submitting}
                  onChange={(event) => {
                    setExperienceRequirements(
                      event.target.value
                    );
                  }}
                  placeholder={
                    'Optional experience requirements'
                  }
                />
              </label>
            </div>

            <div className="createListingNotice">
              Admin-created opportunities use
              the curated publication path.
              They are not attributed to an
              employer account and retain
              server-side admin provenance.
            </div>

            <div className="createListingActions">
              <Link
                className="button buttonSecondary"
                href="/listings"
              >
                Cancel
              </Link>

              <button
                className="button buttonPrimary"
                type="submit"
                disabled={submitting}
              >
                {submitting
                  ? 'Creating...'
                  : publicationStatus
                    === 'published'
                    ? 'Publish opportunity'
                    : 'Save draft'}
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
