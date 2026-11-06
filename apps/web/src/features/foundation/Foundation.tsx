'use client';

import { useEffect, useState } from 'react';
import { Dialog } from '@/components/Dialog';
import { Icon } from '@/components/Icon';
import { PreferenceControls } from '@/components/PreferenceControls';
import { usePreferences } from '@/components/PreferencesProvider';
import { PreviewForm } from './PreviewForm';
import Link from 'next/link';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { useParityText } from '@/features/mobile-parity/useParityText';
import { useBrandText } from '@/features/brand/useBrandText';

export function Foundation() {
  const brand = useBrandText();
  const parity = useParityText();
  const { locale, t } = usePreferences();
  const [role, setRole] = useState<'employer' | 'student'>('employer');
  const [view, setView] = useState<'home' | 'components'>('home');
  const [modal, setModal] = useState<'opportunity' | 'cv' | 'example' | null>(null);
  const [notice, setNotice] = useState('');
  const [noticeId, setNoticeId] = useState(0);
  const student = role === 'student';

  const notify = (message: string) => { setNotice(message); setNoticeId(value => value + 1); };
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 7000);
    return () => clearTimeout(timer);
  }, [notice, noticeId]);

  const number = (value: number) => new Intl.NumberFormat(locale).format(value);
  const metrics = student
    ? [{ label: t.profileStrength, value: `${number(85)}%`, icon: 'target' as const }, { label: t.recommended, value: number(12), icon: 'sparkles' as const }, { label: t.applications, value: number(4), icon: 'file' as const }]
    : [{ label: t.published, value: number(3), icon: 'briefcase' as const }, { label: t.applicants, value: number(24), icon: 'users' as const }, { label: t.underReview, value: number(1), icon: 'file' as const }];

  const navigation = <nav className="workspace-nav" aria-label={t.workspaceNavigation}>
    <button type="button" className={view === 'home' ? 'nav-item active' : 'nav-item'} aria-current={view === 'home' ? 'page' : undefined} onClick={() => setView('home')}><Icon name="home" /><span>{t.home}</span></button>
    <button type="button" className={view === 'components' ? 'nav-item active' : 'nav-item'} aria-current={view === 'components' ? 'page' : undefined} onClick={() => setView('components')}><Icon name="grid" /><span>{t.components}</span></button>
  </nav>;

  return <>
    <a href="#main-content" className="skip-link">{t.skip}</a>
    <div className="workspace">
      <aside className="sidebar">
        <div className="wordmark" dir="ltr"><BrandLogo /></div>
        <div className="sidebar-caption">{t.preview}</div>
        {navigation}
        <div className="sidebar-footer"><span className="mini-mark"><Icon name="target" /></span><p>{t.readyForReview}</p><span>{t.poweredBy}</span></div>
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <div className="mobile-wordmark" dir="ltr"><BrandLogo /></div>
          <p className="breadcrumb">InternMatch AI <span aria-hidden="true">/</span> <strong>{t.foundation}</strong></p>
          <PreferenceControls />
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="review-note"><span className="live-dot" aria-hidden="true" /><p>{t.previewNotice}</p></div>
          <nav className="parity-entry" aria-label={parity.title}><Link href="/review/auth">{parity.authPreview}</Link><Link href="/review/motion">{parity.motionPreview}</Link><Link href="/review/loading">{brand.loadingPreview}</Link></nav>
          <div className="page-heading">
            <div><h1>{view === 'components' ? t.showcaseTitle : student ? brand.studentTitle : brand.employerTitle}</h1><p className="intro">{view === 'components' ? t.showcaseDescription : student ? brand.studentIntro : brand.employerIntro}</p></div>
            <div className="role-switch" role="group" aria-label={t.roleLabel}>
              <button type="button" aria-pressed={role === 'employer'} onClick={() => setRole('employer')}>{t.employer}</button>
              <button type="button" aria-pressed={role === 'student'} onClick={() => setRole('student')}>{t.student}</button>
            </div>
          </div>

          {view === 'home' ? <>
            <div className="metrics-grid">{metrics.map(metric => <section key={metric.label} className="card metric-card"><div className="metric-head"><h2>{metric.label}</h2></div><p className="metric-value">{metric.value}</p></section>)}</div>
            <div className="overview-grid">
              <section className="card work-list"><div className="section-heading"><h2>{student ? brand.recentOpportunities : brand.recentApplicants}</h2><span className="small muted">{t.sample}</span></div>{[86, 79, 72].map((score, index) => <article className="work-row" key={score}><div className="work-row-main"><h3>{student ? t.sampleOpportunity : t.sampleApplicant} <span className="muted">{number(index + 1)}</span></h3><p>{student ? t.sampleCompany : t.sampleRole}</p><span className="small muted">{t.sampleLocation}</span></div><div className="work-row-tail"><span className="work-score" aria-label={`${t.matchLabel}: ${number(score)}%`}>{number(score)}%</span><button type="button" className="work-view" onClick={() => setModal('example')} aria-label={`${brand.view}: ${number(index + 1)}`}>{brand.view}<Icon name="arrow" width="16" height="16" className="directional" /></button></div></article>)}</section>
              <section className="card workspace-actions"><h2>{brand.actions}</h2><p className="muted">{student ? t.uploadBody : t.opportunityBody}</p><button type="button" className="button primary" onClick={() => setModal(student ? 'cv' : 'opportunity')}>{student ? t.uploadAction : t.opportunityAction}<Icon name="arrow" width="18" height="18" className="directional" /></button><div className="workspace-action-note"><span className="small muted">{brand.noData}</span></div></section>
            </div>
          </> : <div className="components-grid">
            <section className="card"><h2>{t.buttons}</h2><div className="showcase-actions"><button type="button" className="button primary" onClick={() => notify(t.previewAction)}>{t.primary}</button><button type="button" className="button secondary" onClick={() => setModal('example')}>{t.openModal}</button><button type="button" className="button secondary" disabled>{t.disabled}</button></div><h3>{t.states}</h3><div className="badge-row"><span className="badge success">{t.statusSuccess}</span><span className="badge warning">{t.statusPending}</span><span className="badge danger">{t.statusError}</span><span className="badge neutral">{t.statusSaved}</span></div><div className="empty-state"><Icon name="sparkles" width="34" height="34" /><h3>{t.emptyTitle}</h3><p className="muted">{t.emptyDescription}</p></div><p className="small muted">{t.keyboardHint}</p></section>
            <section className="card"><h2>{t.formTitle}</h2><PreviewForm key={locale} kind="opportunity" onSuccess={() => notify(t.formSuccess)} /></section>
          </div>}
          <footer className="page-footer"><span>InternMatch AI</span><span>{t.foundation}</span></footer>
        </main>
      </div>
    </div>
    <div className="mobile-navigation">{navigation}</div>
    <div className="toast-region" role="status" aria-live="polite" aria-atomic="true">{notice ? <div className="toast"><Icon name="check" /><span>{notice}</span><button type="button" className="icon-button" onClick={() => setNotice('')} aria-label={t.dismiss}><Icon name="close" /></button></div> : null}</div>
    <Dialog id="preview" open={modal !== null} title={modal === 'cv' ? t.cvFormTitle : modal === 'opportunity' ? t.formTitle : t.modalTitle} onClose={() => setModal(null)}>
      {modal === 'example' ? <><p className="muted dialog-copy">{t.modalDescription}</p><button type="button" className="button primary" onClick={() => setModal(null)}>{t.close}</button></> : modal ? <PreviewForm key={`${modal}-${locale}`} kind={modal} onSuccess={() => { setModal(null); notify(t.formSuccess); }} /> : null}
    </Dialog>
  </>;
}
