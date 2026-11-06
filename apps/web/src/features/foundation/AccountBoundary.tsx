'use client';

import Link from 'next/link';
import { PreferenceControls } from '@/components/PreferenceControls';
import { usePreferences } from '@/components/PreferencesProvider';
import { Icon } from '@/components/Icon';

export function AccountBoundary() {
  const { t } = usePreferences();
  return <main className="account-boundary">
    <PreferenceControls />
    <section className="card account-card">
      <span className="brand-mark"><Icon name="target" width="40" height="40" /></span>
      <p className="eyebrow">InternMatch AI</p>
      <h1>{t.signInTitle}</h1>
      <p className="muted">{t.signInDescription}</p>
      <Link href="/foundation" className="button primary">{t.reviewInterface}<Icon name="arrow" className="directional" /></Link>
      <a href="https://internmatch.college/" className="text-link">{t.backToWebsite}</a>
    </section>
  </main>;
}
