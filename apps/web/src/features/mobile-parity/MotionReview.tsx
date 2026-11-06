'use client';

import Link from 'next/link';
import { useState, useSyncExternalStore } from 'react';
import { PreferenceControls } from '@/components/PreferenceControls';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { BrandedAILoader } from '@/components/mobile/BrandedAILoader';
import { AnimatedScoreRing } from '@/components/mobile/AnimatedScoreRing';
import { MatchIntelligenceOrb } from '@/components/mobile/MatchIntelligenceOrb';
import { MobileTabBar, type NativeTab } from '@/components/mobile/MobileTabBar';
import { PrimaryButton } from '@/components/mobile/PrimaryButton';
import { Reveal } from '@/components/mobile/Reveal';
import { useMobileText, type MobileKey } from './useMobileText';
import { useParityText } from './useParityText';
import { mobileTokens } from '@/theme/mobile-tokens';

function subscribeScroll(callback: () => void) { window.addEventListener('scroll', callback, { passive: true }); return () => window.removeEventListener('scroll', callback); }
export function MotionReview() {
  const p = useParityText(); const { m } = useMobileText();
  const [replay, setReplay] = useState(0);
  const [paused, setPaused] = useState(false);
  const [role, setRole] = useState<'student' | 'employer'>('student');
  const [selected, setSelected] = useState<NativeTab>('home');
  const [pressed, setPressed] = useState(0);
  const scrolled = useSyncExternalStore(subscribeScroll, () => window.scrollY > 12, () => false);
  return <main className={`parity-review ${paused ? 'motion-paused' : ''}`} id="main-content">
    <header className="parity-header"><BrandLogo /><PreferenceControls /></header>
    <div className="parity-breadcrumb"><Link href="/foundation">{p.back}</Link><Link href="/review/auth">{p.authPreview}</Link></div>
    <div className="review-note"><p>{p.review}</p></div>
    <div className="page-heading"><div><h1 className="type-screen-title">{p.title}</h1><p className="intro">{p.description}</p></div><div className="button-row">
      <PrimaryButton onClick={() => setReplay(value => value + 1)}>{p.replay}</PrimaryButton>
      <PrimaryButton outline onClick={() => setPaused(value => !value)} aria-pressed={paused}>{paused ? p.play : p.pause}</PrimaryButton>
    </div></div>

    <div className="parity-motion-grid">
      <section className="card"><h2>{p.motion}</h2><div key={replay} className="motion-examples">
        <Reveal><BrandLogo /><p className="small muted">800ms / 750ms</p></Reveal>
        <div><BrandedAILoader size={42} active={!paused} /><p className="small muted">{mobileTokens.motion.durations.loaderRotation}ms</p></div>
        <div><AnimatedScoreRing score={86} label={p.score} /><p className="small muted">{mobileTokens.motion.durations.scoreRing}ms</p></div>
      </div><h3>{p.press}</h3><p className="muted form-help">{p.pressHint}</p><div className="button-row"><PrimaryButton onClick={() => setPressed(v => v + 1)}>{p.press} · {pressed}</PrimaryButton><PrimaryButton loading>{m('auth.signingIn')}</PrimaryButton></div></section>

      <section className="card"><h2>{p.fonts}</h2><p className="form-help muted">{p.fontNote}</p><div className="type-samples">
        <p className="type-display">{p.displaySample}</p><p className="type-screen-title">{p.displaySample}</p><p className="type-section-title">{p.bodySample}</p><p className="type-card-title">{p.bodySample}</p><p className="type-body">{p.bodySample}</p><p className="type-body-emphasis">{p.bodySample}</p><p className="type-caption">{p.bodySample}</p><p className="type-eyebrow">{p.bodySample}</p><p className="type-button">{p.bodySample}</p><p className="type-badge">{p.bodySample}</p>
      </div></section>
    </div>
    <section className="card parity-orb-section"><h2>{p.states}</h2><div className="orb-grid" key={replay}>
      {(['missing', 'ready', 'calculating', 'matched'] as const).map(state => <div key={state}><h3 className="orb-state-label">{p[state]}</h3><MatchIntelligenceOrb state={state} active={!paused} /></div>)}
    </div></section>

    <section className="card parity-navigation-section"><h2>{p.navigation}</h2>
      <div className="role-switch" role="group" aria-label={p.previewRole}>{(['student', 'employer'] as const).map(value => <button type="button" key={value} aria-pressed={role === value} onClick={() => { setRole(value); setSelected('home'); }}>{m(value === 'student' ? 'auth.intern' : 'auth.employer')}</button>)}</div>
      <p className="form-help muted" role="status">{p.selectedTab}: {m(`navigation.tabs.${selected}` as MobileKey)}</p>
      <MobileTabBar role={role} selected={selected} onSelect={setSelected} scrolled={scrolled} label={p.navigation} />
    </section><footer className="page-footer"><p>{p.details}</p></footer>
  </main>;
}
