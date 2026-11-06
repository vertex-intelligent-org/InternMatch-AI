'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import en from '@/locales/en.json';
import tr from '@/locales/tr.json';
import ar from '@/locales/ar.json';
import { appearanceCookie, localeCookie, type Appearance, type Locale } from '@/lib/preferences';

type Messages = { [Key in keyof typeof en]: string };
const dictionaries: Record<Locale, Messages> = { en, tr, ar };
type Preferences = {
  locale: Locale;
  appearance: Appearance;
  t: Messages;
  setLocale: (value: Locale) => void;
  setAppearance: (value: Appearance) => void;
};
const Context = createContext<Preferences | null>(null);

function saveCookie(name: string, value: string) {
  document.cookie = `${name}=${value}; Path=/app; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
}

export function PreferencesProvider({ children, initialLocale, initialAppearance }: {
  children: React.ReactNode;
  initialLocale: Locale;
  initialAppearance: Appearance;
}) {
  const [locale, updateLocale] = useState(initialLocale);
  const [appearance, updateAppearance] = useState(initialAppearance);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const mode = appearance === 'system' ? (media.matches ? 'dark' : 'light') : appearance;
      document.documentElement.dataset.theme = mode;
      document.documentElement.style.colorScheme = mode;
    };
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [appearance]);

  const setLocale = (value: Locale) => {
    document.documentElement.lang = value;
    document.documentElement.dir = value === 'ar' ? 'rtl' : 'ltr';
    saveCookie(localeCookie, value);
    updateLocale(value);
  };
  const setAppearance = (value: Appearance) => {
    saveCookie(appearanceCookie, value);
    updateAppearance(value);
  };

  return <Context.Provider value={{ locale, appearance, t: dictionaries[locale], setLocale, setAppearance }}>
    {children}
  </Context.Provider>;
}

export function usePreferences() {
  const context = useContext(Context);
  if (!context) throw new Error('PreferencesProvider is required');
  return context;
}
