'use client';
import en from '@/locales/workspace/en.json';import tr from '@/locales/workspace/tr.json';import ar from '@/locales/workspace/ar.json';import {usePreferences} from '@/components/PreferencesProvider';
export function useWorkspaceText(){const {locale}=usePreferences();return {t:{en,tr,ar}[locale],locale};}
