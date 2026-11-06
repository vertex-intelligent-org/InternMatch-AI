import { test, expect, type BrowserContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import en from '../../src/locales/en.json';
import tr from '../../src/locales/tr.json';
import ar from '../../src/locales/ar.json';
import brandEn from '../../src/locales/brand/en.json';
import brandTr from '../../src/locales/brand/tr.json';
import brandAr from '../../src/locales/brand/ar.json';
import authEn from '../../src/locales/auth/en.json';
import mobileEn from '../../src/locales/mobile/en.json';

const dictionaries = { en, tr, ar };
const brand = { en: brandEn, tr: brandTr, ar: brandAr };
const origin = 'http://127.0.0.1:3100';
async function preferences(context: BrowserContext, locale: string, theme: string) {
  await context.addCookies([
    { name: 'im-web-locale', value: locale, domain: '127.0.0.1', path: '/app' },
    { name: 'im-web-appearance', value: theme, domain: '127.0.0.1', path: '/app' },
  ]);
}

for (const locale of ['en', 'tr', 'ar'] as const) {
  const t = dictionaries[locale];
  for (const theme of ['light', 'dark']) {
    for (const width of [360, 768, 1440]) {
      for (const role of ['employer', 'student'] as const) {
        test(`${locale} ${theme} ${width}px ${role}: readable responsive overview`, async ({ page, context }) => {
          const errors: string[] = [];
          page.on('pageerror', error => errors.push(error.message));
          await preferences(context, locale, theme);
          await page.setViewportSize({ width, height: 950 });
          await page.goto('/app/foundation');
          if (role === 'student') await page.getByRole('button', { name: t.student, exact: true }).click();
          await expect(page.locator('html')).toHaveAttribute('lang', locale);
          await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
          await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
          await expect(page.getByRole('heading', { level: 1 })).toHaveText(role === 'student' ? brand[locale].studentTitle : brand[locale].employerTitle);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
          const bar = page.locator(width <= 800 ? '.mobile-navigation' : '.sidebar');
          expect(await bar.evaluate(element => getComputedStyle(element).backgroundColor)).toBe(theme === 'dark' ? 'rgb(11, 57, 71)' : 'rgb(7, 94, 115)');
          expect(errors).toEqual([]);
        });
      }
    }
    test(`${locale} ${theme}: overview and component accessibility`, async ({ page, context }) => {
      await preferences(context, locale, theme);
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto('/app/foundation');
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      await page.getByRole('button', { name: t.components, exact: true }).first().click();
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      await page.getByRole('button', { name: t.openModal, exact: true }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
      expect(await page.getByRole('dialog').evaluate(element => getComputedStyle(element).backgroundColor)).toBe(theme === 'dark' ? 'rgb(16, 50, 58)' : 'rgb(255, 255, 255)');
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).not.toBeVisible();
      await expect(page.getByRole('button', { name: t.openModal, exact: true })).toBeFocused();
    });
  }
}

test('language and theme changes survive a reload; system theme responds to device changes', async ({ page }) => {
  await page.goto('/app/foundation');
  await page.getByRole('button', { name: en.language, exact: true }).click();
  await page.getByRole('button', { name: 'العربية', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await page.getByRole('button', { name: ar.appearance, exact: true }).click();
  await page.getByRole('button', { name: ar.dark, exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: ar.appearance, exact: true }).click();
  await page.getByRole('button', { name: ar.system, exact: true }).click();
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('preview validation keeps identity data local and gives accessible field errors', async ({ page }) => {
  const sent: string[] = [];
  page.on('request', request => { if (request.method() === 'POST') sent.push(request.url()); });
  await page.goto('/app/foundation');
  await page.getByRole('button', { name: en.components, exact: true }).first().click();
  await page.getByRole('button', { name: en.validate, exact: true }).click();
  await expect(page.getByLabel(en.fullName, { exact: true })).toBeFocused();
  await expect(page.getByLabel(en.fullName, { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await page.getByLabel(en.fullName, { exact: true }).fill('Çağrı Öğrenci');
  await page.getByLabel(en.email, { exact: true }).fill('preview@example.com');
  await page.getByLabel(en.opportunityName, { exact: true }).fill('فرصة تدريب');
  await page.getByRole('button', { name: en.validate, exact: true }).click();
  await expect(page.getByRole('status')).toContainText(en.formSuccess);
  expect(sent).toEqual([]);
});

test('CV chooser handles Unicode names locally, rejects invalid files and requires notice confirmation', async ({ page }) => {
  await page.goto('/app/foundation');
  await page.getByRole('button', { name: en.student, exact: true }).click();
  await page.getByRole('button', { name: en.uploadAction, exact: true }).click();
  const input = page.getByLabel(en.fileLabel, { exact: true });
  await input.setInputFiles({ name: 'السيرة_Çağrı.txt', mimeType: 'text/plain', buffer: Buffer.from('sample') });
  await expect(page.locator('#file-error')).toHaveText(en.fileInvalid);
  await input.setInputFiles({ name: 'السيرة_Çağrı.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-preview') });
  await page.getByRole('button', { name: en.validate, exact: true }).click();
  await expect(page.locator('#consent-error')).toHaveText(en.consentRequired);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: en.validate, exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('status')).toContainText(en.formSuccess);
});

test('unconfigured authentication stays disabled; base path assets stay within /app', async ({ page }) => {
  const missing: string[] = [];
  page.on('response', response => { if (response.status() >= 400 && response.url().startsWith(origin)) missing.push(response.url()); });
  await page.goto('/app/sign-in');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(mobileEn['auth.welcomeBack']);
  await expect(page.locator('input[type=password]')).toBeDisabled();
  await expect(page.getByText(authEn.notConfigured, { exact: true })).toBeVisible();
  await page.getByRole('link', { name: authEn.interfacePreview }).click();
  await expect(page).toHaveURL(/\/app\/foundation$/);
  const assets = await page.locator('script[src]').evaluateAll(elements => elements.map(element => element.getAttribute('src')));
  expect(assets.every(src => src?.startsWith('/app/_next/'))).toBe(true);
  expect(missing).toEqual([]);
});

test('320px Arabic layout retains all controls without horizontal overflow', async ({ page, context }) => {
  await preferences(context, 'ar', 'dark');
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto('/app/foundation');
  await page.getByRole('button', { name: ar.language, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Türkçe', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: ar.components, exact: true }).last().click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
