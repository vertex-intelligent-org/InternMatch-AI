import { test, expect, type BrowserContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import en from '../../src/locales/brand/en.json';
import tr from '../../src/locales/brand/tr.json';
import ar from '../../src/locales/brand/ar.json';
import mobile from '../../src/locales/mobile/en.json';

const labels = { en, tr, ar };
async function preferences(context: BrowserContext, locale: string, theme: string) {
  await context.addCookies([
    { name: 'im-web-locale', value: locale, domain: '127.0.0.1', path: '/app' },
    { name: 'im-web-appearance', value: theme, domain: '127.0.0.1', path: '/app' },
  ]);
}
for (const locale of ['en', 'tr', 'ar'] as const) {
  for (const theme of ['light', 'dark']) {
    test(`${locale} ${theme}: actual local fonts, neutral canvas and 320px layout`, async ({ page, context }) => {
      await preferences(context, locale, theme);
      await page.setViewportSize({ width: 320, height: 900 });
      const external: string[] = [];
      page.on('request', r => { if (!r.url().startsWith('http://127.0.0.1:3100') && /^https?:/.test(r.url())) external.push(r.url()); });
      await page.goto('/app/foundation');
      const fonts = await page.evaluate(async () => {
        const family = document.documentElement.lang === 'ar' ? 'Cairo' : 'Bricolage Grotesque';
        const sample = family === 'Cairo' ? 'العربية والتدريب المهني' : 'Türkçe Öğrenci Çığ Şİ';
        const loaded = await document.fonts.load(`400 16px "${family}"`, sample);
        await document.fonts.ready;
        return { family: getComputedStyle(document.body).fontFamily, loaded: loaded.map(face => face.status), background: getComputedStyle(document.documentElement).backgroundColor };
      });
      expect(fonts.family).toContain(locale === 'ar' ? 'Cairo' : 'Bricolage Grotesque');
      expect(fonts.loaded.length).toBeGreaterThan(0); expect(fonts.loaded.every(s => s === 'loaded')).toBe(true);
      expect(fonts.background).toBe(theme === 'light' ? 'rgb(247, 247, 245)' : 'rgb(6, 25, 31)');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(external).toEqual([]);
    });
    test(`${locale} ${theme}: waiting scene is readable and accessible`, async ({ page, context }) => {
      await preferences(context, locale, theme); await page.goto('/app/review/loading');
      await page.getByRole('button', { name: labels[locale].simulateFive, exact: true }).click();
      await expect(page.locator('.pending-region')).toHaveAttribute('aria-busy', 'true');
      await expect(page.locator('.wait-content')).toBeVisible();
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    });
  }
  test(`${locale}: waiting disappears when the operation finishes`, async ({ page, context }) => {
    await preferences(context, locale, 'light'); await page.goto('/app/review/loading');
    // Measure the operation timer, independent of host load and Playwright IPC.
    await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') });
    await page.clock.pauseAt(new Date('2026-01-01T00:00:01Z'));
    await page.getByRole('button', { name: labels[locale].simulateTwo, exact: true }).click();
    await expect(page.locator('.pending-region')).toHaveAttribute('aria-busy', 'true');
    await page.clock.runFor(300);
    await expect(page.locator('.wait-content')).toBeVisible();
    await page.clock.runFor(1600);
    await expect(page.locator('.pending-region')).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('.loading-ready')).toHaveCount(0);
    await page.clock.runFor(100);
    await expect(page.locator('.loading-ready')).toBeVisible();
    await expect(page.locator('.pending-region')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('.wait-content')).toHaveCount(0);
  });
}

test('direct entry selects signup; invalid mode falls back to sign in', async ({ page }) => {
  await page.goto('/app/review/auth?mode=sign-up');
  await expect(page.getByRole('tab', { name: mobile['auth.segmentedSignUp'], exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('form input:disabled')).toHaveCount(4);
  await page.goto('/app/review/auth?mode=unknown');
  await expect(page.getByRole('tab', { name: mobile['auth.segmentedSignIn'], exact: true })).toHaveAttribute('aria-selected', 'true');
});

test('reduced-motion waiting retains wordmark with no arrow flight or target rotation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.goto('/app/review/loading');
  await page.getByRole('button', { name: en.simulateFive, exact: true }).click();
  await expect(page.locator('.wait-content .bow-brand-scene')).toHaveAttribute('data-phase', 'static');
  await expect(page.locator('.wait-content .bow-brand-wordmark')).toHaveText('InternMatch AI');
  expect(await page.locator('.wait-content .bow-target-wheel').evaluate(e => getComputedStyle(e).animationName)).toBe('none');
});

test('bow flight settles while a longer operation remains pending; ready state is static', async ({ page }) => {
  await page.goto('/app/review/loading');
  await page.getByRole('button', { name: en.simulateFive, exact: true }).click();
  const scene = page.locator('.wait-content .bow-brand-scene');
  await expect(scene).toHaveAttribute('data-phase', 'settled', { timeout: 3200 });
  await expect(page.locator('.pending-region')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('.wait-content .bow-target-impact')).toHaveClass(/has-impact/);
  await expect(page.locator('.loading-ready')).toBeVisible({ timeout: 3500 });
  await expect(page.locator('.loading-ready .bow-brand-scene')).toHaveAttribute('data-phase', 'static');
});
