'use client';
import { usePreferences } from '@/components/PreferencesProvider';
import en from '@/locales/parity/en.json';
import tr from '@/locales/parity/tr.json';
import ar from '@/locales/parity/ar.json';
const dictionaries = { en, tr, ar };
export function useParityText() { const { locale } = usePreferences(); return dictionaries[locale]; }
