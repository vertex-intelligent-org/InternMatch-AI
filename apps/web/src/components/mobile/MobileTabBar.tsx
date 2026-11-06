'use client';

import { useEffect, useRef } from 'react';
import { useMobileText, type MobileKey } from '@/features/mobile-parity/useMobileText';
import { MobileIcon, type MobileIconName } from './MobileIcon';
import { useReducedMotion } from './useReducedMotion';
import { springSamples } from './spring';

export const studentTabs = ['home', 'internships', 'matchups', 'applications', 'profile'] as const;
export const employerTabs = ['home', 'opportunities', 'profile'] as const;
export type NativeTab = typeof studentTabs[number] | typeof employerTabs[number];
const icons: Record<NativeTab, MobileIconName> = { home: 'home', internships: 'business', opportunities: 'briefcase', matchups: 'radio-button-on', applications: 'document-text', profile: 'person-circle' };

export function MobileTabBar({ role, selected, onSelect, scrolled = false, label }: { role: 'student' | 'employer'; selected: NativeTab; onSelect: (tab: NativeTab) => void; scrolled?: boolean; label: string }) {
  const { m, locale } = useMobileText();
  const tabs = role === 'student' ? studentTabs : employerTabs;
  const group = useRef<HTMLDivElement>(null);
  const lens = useRef<HTMLSpanElement>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const position = useRef<number | null>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    let animation: Animation | undefined;
    const update = () => {
      const button = buttons.current[selected]; const target = lens.current;
      if (!button || !target) return;
      const width = Math.max(48, button.offsetWidth - 8);
      const left = button.offsetLeft + (button.offsetWidth - width) / 2;
      target.style.width = `${width}px`;
      target.style.transform = `translateX(${left}px)`;
      animation?.cancel();
      if (!reduced && position.current !== null && target.animate) {
        animation = target.animate(springSamples(position.current, left, { damping: 26, stiffness: 300, mass: .7 }).map(x => ({ transform: `translateX(${x}px)` })), { duration: 800 });
      }
      position.current = left;
    };
    update();
    const observer = new ResizeObserver(update);
    if (group.current) observer.observe(group.current);
    return () => { observer.disconnect(); animation?.cancel(); };
  }, [selected, role, locale, reduced]);
  return <div className={`native-tab-bar ${scrolled ? 'is-scrolled' : ''}`} data-native-role={role}>
    <div ref={group} className="native-tabs" role="group" aria-label={label}>
      <span ref={lens} className="native-tab-lens" aria-hidden="true" />
      {tabs.map(tab => <button key={tab} ref={element => { buttons.current[tab] = element; }} type="button" className="native-tab" aria-pressed={selected === tab} aria-label={m(`navigation.tabs.${tab}` as MobileKey)} onClick={() => onSelect(tab)}>
        <MobileIcon name={icons[tab]} /><span className="native-tab-dot" aria-hidden="true" />
      </button>)}
    </div>
  </div>;
}
