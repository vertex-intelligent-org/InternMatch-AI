export const locales = ['en', 'tr', 'ar'] as const;
export type Locale = typeof locales[number];
export type Appearance = 'system' | 'light' | 'dark';
export const localeCookie = 'im-web-locale';
export const appearanceCookie = 'im-web-appearance';

export function validLocale(value?: string): Locale | undefined {
  return locales.find(locale => locale === value);
}

export function validAppearance(value?: string): Appearance {
  return value === 'dark' || value === 'light' ? value : 'system';
}

export function browserLocale(header: string): Locale {
  for (const part of header.split(',')) {
    const language = part.split(';')[0].trim().split('-')[0].toLowerCase();
    const locale = validLocale(language);
    if (locale) return locale;
  }
  return 'en';
}
