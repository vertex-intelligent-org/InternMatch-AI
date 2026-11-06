'use client';

import { useState } from 'react';
import { Dialog } from './Dialog';
import { Icon } from './Icon';
import { usePreferences } from './PreferencesProvider';
import type { Appearance, Locale } from '@/lib/preferences';

export function PreferenceControls({ showLanguage = true }: { showLanguage?: boolean }) {
  const { locale, appearance, t, setLocale, setAppearance } = usePreferences();
  const [open, setOpen] = useState<'language' | 'appearance' | null>(null);
  const languages: { code: Locale; label: string }[] = [
    { code: 'en', label: 'English' }, { code: 'tr', label: 'Türkçe' }, { code: 'ar', label: 'العربية' },
  ];
  const modes: Appearance[] = ['light', 'dark', 'system'];

  return <>
    <div className="preference-controls">
      {showLanguage ? <button type="button" className="control-button" aria-label={t.language} aria-haspopup="dialog" onClick={() => setOpen('language')}>
        <Icon name="globe" /><span lang={locale}>{languages.find(item => item.code === locale)?.label}</span>
      </button> : null}
      <button type="button" className="control-button theme-control" aria-label={t.appearance} aria-haspopup="dialog" onClick={() => setOpen('appearance')}>
        <Icon name={appearance === 'dark' ? 'moon' : 'sun'} /><span>{t.appearance}</span>
      </button>
    </div>
    <Dialog id="language" title={t.language} open={open === 'language'} onClose={() => setOpen(null)}>
      <div className="choice-list">
        {languages.map(item => <button key={item.code} type="button" className="choice" aria-pressed={locale === item.code} onClick={() => { setLocale(item.code); setOpen(null); }}>
          <span lang={item.code} dir={item.code === 'ar' ? 'rtl' : 'ltr'}>{item.label}</span>
          {locale === item.code ? <Icon name="check" /> : null}
        </button>)}
      </div>
    </Dialog>
    <Dialog id="appearance" title={t.appearance} open={open === 'appearance'} onClose={() => setOpen(null)}>
      <div className="choice-list">
        {modes.map(mode => <button key={mode} type="button" className="choice" aria-pressed={appearance === mode} onClick={() => { setAppearance(mode); setOpen(null); }}>
          <span>{t[mode]}</span>{appearance === mode ? <Icon name="check" /> : null}
        </button>)}
      </div>
    </Dialog>
  </>;
}
