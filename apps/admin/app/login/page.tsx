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

function errorMessage(error: unknown): string {
  if (
    error instanceof ApiError
    || error instanceof AdminConfigurationError
    || error instanceof Error
  ) {
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
                  ? 'This account is not authorized for administrative access.'
                  : 'Your administrative session is no longer valid.'
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
              ? 'This account is authenticated but is not in the server administrator allowlist.'
              : 'The new session could not be verified by the API.'
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
              <span>Admin Console</span>
            </div>
          </div>

          <div className="checkingSession">
            <span
              className="spinner"
              aria-hidden="true"
            />
            Verifying session?
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
            <span>Admin Console</span>
          </div>
        </div>

        <div className="loginHeading">
          <p className="eyebrow">
            Restricted access
          </p>
          <h1>
            Sign in to the verification console
          </h1>
          <p>
            Authentication uses your InternMatch
            Supabase account. Administrative
            authority is verified separately by
            the API.
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
              ? 'Verifying access?'
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
