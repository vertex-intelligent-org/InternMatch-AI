'use client';

import { useMobileText } from '@/features/mobile-parity/useMobileText';
import { MobileIcon } from './MobileIcon';
import { Reveal } from './Reveal';

export type OrbState = 'missing' | 'ready' | 'calculating' | 'matched';
export function MatchIntelligenceOrb({ state = 'missing', score = 86, progress = 42, active = true }: { state?: OrbState; score?: number; progress?: number; active?: boolean }) {
  const { m } = useMobileText();
  const safeScore = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0));
  const safeProgress = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
  const calculating = state === 'calculating';
  const label = calculating ? m('orb.a11yCalculating', { progress: safeProgress }) : state === 'matched' ? m('orb.a11yTop', { score: safeScore }) : state === 'ready' ? m('orb.a11yReady') : m('orb.a11yCvNeeded');
  return <div className={`orb-wrapper ${calculating && active ? 'pulse-active' : ''}`}>
    <Reveal className="native-orb" variant="hero" role="img" aria-label={label}>
      <div className="orb-badge"><span aria-hidden="true" />{m(calculating ? 'orb.progressEyebrow' : 'orb.eyebrow')}</div>
      <div className="orb-outer"><div className="orb-inner">
        {calculating || state === 'matched' ? <><strong dir="ltr">{calculating ? safeProgress : safeScore}%</strong><small>{m(calculating ? 'orb.analyzing' : 'orb.topMatch')}</small></> : <><MobileIcon name={state === 'ready' ? 'radio-button-on' : 'document-text'} width="30" height="30" /><span>{m(state === 'ready' ? 'orb.ready' : 'orb.cvNeeded')}</span></>}
      </div></div>
      <p>{m(calculating ? 'orb.comparing' : state === 'matched' ? 'orb.compatibilityBackground' : state === 'ready' ? 'orb.readySubtitle' : 'orb.cvNeededSubtitle')}</p>
    </Reveal>
  </div>;
}
