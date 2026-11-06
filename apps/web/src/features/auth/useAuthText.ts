'use client';
import { usePreferences } from '@/components/PreferencesProvider';
import en from '@/locales/auth/en.json';
import tr from '@/locales/auth/tr.json';
import ar from '@/locales/auth/ar.json';
const messages = { en, tr, ar };
export type AuthMessage = keyof typeof en;
export function useAuthText() { const { locale } = usePreferences(); return messages[locale]; }
