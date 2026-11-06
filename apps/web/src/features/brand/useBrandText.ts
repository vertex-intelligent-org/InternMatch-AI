'use client';
import { usePreferences } from '@/components/PreferencesProvider';
import en from '@/locales/brand/en.json';
import tr from '@/locales/brand/tr.json';
import ar from '@/locales/brand/ar.json';
const dictionaries = { en, tr, ar };
export function useBrandText() { const { locale } = usePreferences(); return dictionaries[locale]; }
