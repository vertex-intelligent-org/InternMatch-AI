import Head from 'next/head';


const requestHref =
  'mailto:internmatch@vertexintelligent.com'
  + '?subject=InternMatch%20AI%20Account%20Deletion%20Request'
  + '&body=Hello%20InternMatch%20AI%20Support%2C%0A%0A'
  + 'I%20would%20like%20to%20request%20permanent%20deletion%20'
  + 'of%20my%20InternMatch%20AI%20account.%0A%0A'
  + 'Account%20email%3A%20%0A%0A'
  + 'Please%20do%20not%20include%20passwords%2C%20CVs%2C%20'
  + 'identity%20documents%2C%20or%20other%20sensitive%20files.';


export default function DataDeletionPage() {
  return (
    <>
      <Head>
        <title>
          Delete Your InternMatch AI Account
        </title>

        <meta
          name="description"
          content={
            'Request permanent deletion of your InternMatch AI '
            + 'account and associated product data.'
          }
        />

        <meta
          name="robots"
          content="index,follow"
        />
      </Head>

      <main style={styles.page}>
        <section style={styles.card}>
          <p style={styles.eyebrow}>
            InternMatch AI · VERTEX AI
          </p>

          <h1 style={styles.title}>
            Delete your InternMatch AI account
          </h1>

          <p style={styles.lead}>
            You can permanently delete your InternMatch AI
            account and associated product data under our
            control.
          </p>

          <div style={styles.section}>
            <h2 style={styles.heading}>
              Delete directly in the app
            </h2>

            <p style={styles.text}>
              If you still have access to InternMatch AI,
              open Settings, choose Delete Account, confirm
              the deletion, and complete the identity
              verification step.
            </p>

            <p style={styles.text}>
              The in-app flow permanently deletes the
              account rather than temporarily disabling it.
            </p>
          </div>

          <div style={styles.section}>
            <h2 style={styles.heading}>
              Request deletion without the app
            </h2>

            <p style={styles.text}>
              If you no longer have the app or cannot access
              the in-app deletion flow, you can request
              account deletion using the link below.
            </p>

            <a
              href={requestHref}
              style={styles.primaryButton}
            >
              Request account deletion
            </a>

            <p style={styles.smallText}>
              Send the request from your account email when
              possible, or include the email address used for
              your InternMatch AI account. We may need to
              verify account ownership before processing the
              deletion.
            </p>

            <p style={styles.smallText}>
              Never send your password, authentication
              codes, CV, identity documents, or other
              sensitive files with a deletion request.
            </p>
          </div>

          <div style={styles.section}>
            <h2 style={styles.heading}>
              What deletion covers
            </h2>

            <p style={styles.text}>
              Account deletion removes the InternMatch AI
              account and associated product data under our
              control, including applicable profile and
              account information.
            </p>

            <p style={styles.text}>
              Limited information may be retained when
              necessary for security, fraud prevention,
              dispute handling, regulatory requirements, or
              other legal obligations. Our systems may also
              retain minimal deletion-state records needed
              to prevent deleted subscription authority from
              being recreated by delayed provider events.
            </p>
          </div>

          <div style={styles.section}>
            <h2 style={styles.heading}>
              App Store and Google Play subscriptions
            </h2>

            <p style={styles.text}>
              Deleting your InternMatch AI account does not
              automatically cancel a subscription billed by
              Apple App Store or Google Play.
            </p>

            <p style={styles.text}>
              Store subscriptions must be managed separately
              through the applicable store account.
            </p>
          </div>

          <div style={styles.section}>
            <h2 style={styles.heading}>
              Need help?
            </h2>

            <p style={styles.text}>
              Contact{' '}
              <a
                href="mailto:internmatch@vertexintelligent.com"
                style={styles.link}
              >
                internmatch@vertexintelligent.com
              </a>
              .
            </p>

            <p style={styles.smallText}>
              If a deletion request requires additional
              processing time, we will communicate the next
              steps after account ownership is verified.
            </p>
          </div>

          <footer style={styles.footer}>
            InternMatch AI is developed by VERTEX AI.
          </footer>
        </section>
      </main>
    </>
  );
}


const styles = {
  page: {
    minHeight: '100vh',
    margin: 0,
    padding: '48px 20px',
    background:
      'linear-gradient(180deg, #07111f 0%, #0b1728 100%)',
    color: '#f5f8ff',
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, '
      + 'BlinkMacSystemFont, "Segoe UI", sans-serif',
    boxSizing: 'border-box',
  },

  card: {
    maxWidth: 820,
    margin: '0 auto',
    padding: '44px 38px',
    border: '1px solid #273950',
    borderRadius: 22,
    backgroundColor: '#0d1b2d',
    boxShadow:
      '0 24px 80px rgba(0, 0, 0, 0.28)',
  },

  eyebrow: {
    margin: '0 0 12px',
    color: '#8fc7ff',
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: '0.04em',
  },

  title: {
    margin: '0 0 18px',
    fontSize: 'clamp(32px, 5vw, 48px)',
    lineHeight: 1.08,
  },

  lead: {
    margin: '0 0 34px',
    color: '#c7d7ea',
    fontSize: 18,
    lineHeight: 1.65,
  },

  section: {
    padding: '26px 0',
    borderTop: '1px solid #22344a',
  },

  heading: {
    margin: '0 0 12px',
    fontSize: 22,
  },

  text: {
    margin: '0 0 14px',
    color: '#c7d7ea',
    fontSize: 16,
    lineHeight: 1.65,
  },

  smallText: {
    margin: '16px 0 0',
    color: '#9fb2c9',
    fontSize: 14,
    lineHeight: 1.6,
  },

  primaryButton: {
    display: 'inline-block',
    marginTop: 4,
    padding: '14px 20px',
    borderRadius: 12,
    backgroundColor: '#f5f8ff',
    color: '#07111f',
    fontWeight: 800,
    textDecoration: 'none',
  },

  link: {
    color: '#8fc7ff',
  },

  footer: {
    paddingTop: 24,
    borderTop: '1px solid #22344a',
    color: '#8297b0',
    fontSize: 13,
  },
};