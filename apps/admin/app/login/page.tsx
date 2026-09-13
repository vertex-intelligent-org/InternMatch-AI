'use client';

import {
  FormEvent,
  useEffect,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';

import {
  ApiError,
  listOrganizationsForReview,
} from '../../lib/api';
import {
  AdminConfigurationError,
  getSupabaseClient,
} from '../../lib/supabase';

function errorMessage(
  error: unknown
): string {
  if (error instanceof AdminConfigurationError) {
    return (
      'This admin workspace is not fully '
      + 'configured on this device yet.'
    );
  }

  if (error instanceof ApiError) {
    if (
      error.code === 'API_NOT_CONFIGURED'
    ) {
      return (
        'The InternMatch admin service is not '
        + 'connected yet. Please complete the '
        + 'local setup and try again.'
      );
    }

    if (
      error.code === 'NETWORK_ERROR'
      || error.status === 0
    ) {
      return (
        'We cannot reach the InternMatch admin '
        + 'service right now. Please try again.'
      );
    }

    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Unable to complete the request.';
}

export default function AdminLoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] =
    useState('');
  const [error, setError] =
    useState<string | null>(null);
  const [submitting, setSubmitting] =
    useState(false);
  const [checkingSession, setCheckingSession] =
    useState(true);

  useEffect(() => {
    let active = true;

    async function restoreSession() {
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
          setError(sessionError.message);
          setCheckingSession(false);
          return;
        }

        if (!data.session) {
          setCheckingSession(false);
          return;
        }

        try {
          await listOrganizationsForReview(
            'pending'
          );

          if (active) {
            router.replace('/');
          }
        } catch (requestError) {
          if (
            requestError instanceof ApiError
            && (
              requestError.status === 401
              || requestError.status === 403
            )
          ) {
            await supabase.auth.signOut();

            if (active) {
              setError(
                requestError.status === 403
                  ? 'This account does not have permission to open the admin workspace.'
                  : 'Your admin session has expired. Please sign in again.'
              );
              setCheckingSession(false);
            }

            return;
          }

          if (active) {
            setError(
              errorMessage(requestError)
            );
            setCheckingSession(false);
          }
        }
      } catch (configurationError) {
        if (active) {
          setError(
            errorMessage(
              configurationError
            )
          );
          setCheckingSession(false);
        }
      }
    }

    void restoreSession();

    return () => {
      active = false;
    };
  }, [router]);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setError(null);
    setSubmitting(true);

    try {
      const supabase =
        getSupabaseClient();

      const {
        error: signInError,
      } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (signInError) {
        setError(signInError.message);
        return;
      }

      try {
        await listOrganizationsForReview(
          'pending'
        );
      } catch (requestError) {
        if (
          requestError instanceof ApiError
          && (
            requestError.status === 401
            || requestError.status === 403
          )
        ) {
          await supabase.auth.signOut();

          setError(
            requestError.status === 403
              ? 'This account does not have permission to open the admin workspace.'
              : 'We could not verify this admin session. Please sign in again.'
          );

          return;
        }

        throw requestError;
      }

      router.replace('/');
    } catch (requestError) {
      setError(
        errorMessage(requestError)
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (checkingSession) {
    return (
      <main className="loginPage">
        <section
          className="loginCard"
          aria-live="polite"
        >
          <div className="loginBrand">
            <span className="brandMark">
              IM
            </span>
            <div>
              <strong>InternMatch</strong>
              <span>Trust Console</span>
            </div>
          </div>

          <div className="checkingSession">
            <span
              className="spinner"
              aria-hidden="true"
            />
            Preparing your workspace?
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="loginPage">
      <section className="loginCard">
        <div className="loginBrand">
          <span className="brandMark">
            IM
          </span>
          <div>
            <strong>InternMatch</strong>
            <span>Trust Console</span>
          </div>
        </div>

        <div className="loginHeading">
          <p className="eyebrow">
            InternMatch Admin
          </p>
          <h1>
            Welcome back
          </h1>
          <p>
            Sign in to continue to your
            InternMatch trust workspace.
            Administrative access is checked
            securely before the console opens.
          </p>
        </div>

        <form
          className="form"
          onSubmit={handleSubmit}
        >
          <label className="formField">
            <span>Email</span>
            <input
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(
                  event.target.value
                );
              }}
            />
          </label>

          <label className="formField">
            <span>Password</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(
                  event.target.value
                );
              }}
            />
          </label>

          {error ? (
            <div
              className="errorBox"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          <button
            className="button buttonPrimary buttonFull"
            type="submit"
            disabled={submitting}
          >
            {submitting
              ? 'Verifying access...'
              : 'Sign in securely'}
          </button>
        </form>

        <p className="loginFootnote">
          Access is denied unless the authenticated
          user is authorized by the server-side
          administrator allowlist.
        </p>
      </section>
    </main>
  );
}
