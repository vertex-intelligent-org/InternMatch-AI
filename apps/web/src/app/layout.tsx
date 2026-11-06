import type { Metadata, Viewport } from 'next';
import { cookies, headers } from 'next/headers';
import { PreferencesProvider } from '@/components/PreferencesProvider';
import { appearanceCookie, browserLocale, localeCookie, validAppearance, validLocale } from '@/lib/preferences';
import './globals.css';
import '@/theme/mobile.css';
import '@/theme/brand-fonts.css';
import '@/theme/brand.css';
import '@/theme/auth.css';
import '@/theme/student.css';
import '@/theme/workspace.css';

export const metadata: Metadata = {
  title: 'InternMatch AI · Web Preview',
  description: 'InternMatch AI web interface foundation preview.',
  robots: { index: false, follow: false },
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [jar, requestHeaders] = await Promise.all([cookies(), headers()]);
  const locale = validLocale(jar.get(localeCookie)?.value) ?? browserLocale(requestHeaders.get('accept-language') ?? '');
  const appearance = validAppearance(jar.get(appearanceCookie)?.value);
  const mode = appearance === 'dark' ? 'dark' : 'light';
  // Only a validated enum is interpolated; no user-provided script content.
  const themeScript = `(()=>{const a=${JSON.stringify(appearance)};const m=a==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):a;document.documentElement.dataset.theme=m;document.documentElement.style.colorScheme=m})()`;

  return <html lang={locale} dir={locale === 'ar' ? 'rtl' : 'ltr'} data-theme={mode} suppressHydrationWarning>
    <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
    <body><PreferencesProvider initialLocale={locale} initialAppearance={appearance}>{children}</PreferencesProvider></body>
  </html>;
}
