'use client';
import en from '@/locales/student/en.json';
import tr from '@/locales/student/tr.json';
import ar from '@/locales/student/ar.json';
import { usePreferences } from '@/components/PreferencesProvider';
export function useStudentText(){const {locale}=usePreferences();return {t:{en,tr,ar}[locale],locale};}
