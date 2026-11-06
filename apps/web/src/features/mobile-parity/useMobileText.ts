'use client';

import { usePreferences } from '@/components/PreferencesProvider';
import en from '@/locales/mobile/en.json';
import tr from '@/locales/mobile/tr.json';
import ar from '@/locales/mobile/ar.json';

const dictionaries = { en, tr, ar };
export type MobileKey = keyof typeof en;
export function useMobileText() {
  const { locale } = usePreferences();
  return { locale, m: (key: MobileKey, values: Record<string, string | number> = {}) => dictionaries[locale][key].replace(/\{\{(\w+)\}\}/g, (match, name: string) => String(values[name] ?? match)) };
}
