import { test, expect, type BrowserContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import en from '../../src/locales/mobile/en.json';
import tr from '../../src/locales/mobile/tr.json';
import ar from '../../src/locales/mobile/ar.json';
import labelsEn from '../../src/locales/parity/en.json';
import labelsTr from '../../src/locales/parity/tr.json';
import labelsAr from '../../src/locales/parity/ar.json';

const dictionaries = { en, tr, ar };
const labels = { en: labelsEn, tr: labelsTr, ar: labelsAr };
async function preferences(context: BrowserContext, locale: string, theme: string) {
  await context.addCookies([
    { name: 'im-web-locale', value: locale, domain: '127.0.0.1', path: '/app' },
    { name: 'im-web-appearance', value: theme, domain: '127.0.0.1', path: '/app' },
  ]);
}

for (const locale of ['en', 'tr', 'ar'] as const) {
  const t = dictionaries[locale]; const p = labels[locale];
  for (const theme of ['light', 'dark']) {
    for (const width of [320, 390, 768, 1440]) {
      test(`${locale} ${theme} ${width}px: auth visual layout, role gate and accessible controls`, async ({ page, context }) => {
        const failures: string[] = [];
        page.on('pageerror', error => failures.push(error.message));
        await preferences(context, locale, theme);
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/app/review/auth');
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(t['auth.welcomeBack']);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.getByRole('tab', { name: t['auth.segmentedSignUp'], exact: true }).click();
        await expect(page.locator('form input:disabled')).toHaveCount(4);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.locator('.role-lock-overlay').first().click();
        await expect(page.locator('#role-guidance')).toHaveAttribute('role', 'alert');
        await expect(page.locator('#role-guidance')).toHaveText(t['auth.selectAccountType']);
        await expect(page.getByRole('radio', { name: t['auth.intern'], exact: true })).toBeFocused();
        await page.getByRole('radio', { name: t['auth.employer'], exact: true }).check();
        await expect(page.locator('form input:disabled')).toHaveCount(0);
        await expect(page.locator('.native-social')).toHaveCount(0);
        await page.getByRole('radio', { name: t['auth.intern'], exact: true }).check();
        await expect(page.locator('.native-social')).toHaveCount(2);
        await expect(page.getByRole('button', { name: p.showPassword })).toBeVisible();
        expect(failures).toEqual([]);
      });
    }
    test(`${locale} ${theme}: auth accessibility in both account modes`, async ({ page, context }) => {
      await preferences(context, locale, theme); await page.goto('/app/review/auth');
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      await page.getByRole('tab', { name: t['auth.segmentedSignUp'], exact: true }).click();
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      await page.getByRole('radio', { name: t['auth.employer'], exact: true }).check();
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    });
    test(`${locale} ${theme}: native motion geometry, colors, directions and font metrics`, async ({ page, context }) => {
      await preferences(context, locale, theme); await page.setViewportSize({ width: 390, height: 850 });
      await page.goto('/app/review/motion');
      await expect(page.locator('.native-tab')).toHaveCount(5);
      expect(await page.locator('.native-tab-bar').evaluate(e => getComputedStyle(e).backgroundColor)).toBe(theme === 'dark' ? 'rgb(11, 57, 71)' : 'rgb(7, 94, 115)');
      await page.getByRole('button', { name: t['navigation.tabs.matchups'], exact: true }).click();
      await page.waitForTimeout(900);
      const geometry = await page.evaluate(() => {
        const bar = document.querySelector('.native-tab-bar')!.getBoundingClientRect();
        const lens = document.querySelector('.native-tab-lens')!.getBoundingClientRect();
        const tab = document.querySelector('.native-tab[aria-pressed="true"]')!.getBoundingClientRect();
        return { bar: bar.height, lens: lens.height, aligned: Math.abs((lens.x + lens.width / 2) - (tab.x + tab.width / 2)) < 2 };
      });
      expect(geometry).toEqual({ bar: 60, lens: 48, aligned: true });
      const type = await page.locator('.type-display').evaluate(e => { const s = getComputedStyle(e); return [s.fontSize, s.lineHeight, s.fontWeight, s.fontFamily]; });
      expect(type.slice(0, 3)).toEqual(['26px', '32px', '700']);
      expect(type[3]).toContain(locale === 'ar' ? 'Cairo' : 'Bricolage Grotesque');
      expect(await page.locator('.is-active .loader-rotation').evaluate(e => getComputedStyle(e).animationDuration)).toBe('2.4s');
      await page.getByRole('button', { name: t['auth.employer'], exact: true }).click();
      await expect(page.locator('.native-tab')).toHaveCount(3);
      await page.getByRole('button', { name: t['navigation.tabs.profile'], exact: true }).click();
      await page.getByRole('heading', { name: p.navigation, exact: true }).scrollIntoViewIfNeeded();
      await expect(page.locator('.native-tab-bar')).toHaveClass(/is-scrolled/);
      expect(await page.locator('.native-tab-bar').evaluate(e => getComputedStyle(e).backgroundColor)).toBe(theme === 'dark' ? 'rgb(9, 45, 56)' : 'rgb(7, 80, 105)');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}

test('auth preview persists Unicode locale and never posts sample credentials', async ({ page }) => {
  const posts: string[] = []; page.on('request', r => { if (r.method() === 'POST') posts.push(r.url()); });
  await page.goto('/app/review/auth');
  await page.getByRole('button', { name: 'Language', exact: true }).click();
  await page.getByRole('button', { name: 'TR', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'tr');
  await page.reload(); await expect(page.locator('html')).toHaveAttribute('lang', 'tr');
  await page.getByRole('tab', { name: tr['auth.segmentedSignUp'], exact: true }).click();
  await page.getByRole('radio', { name: tr['auth.intern'], exact: true }).check();
  await page.getByLabel(tr['auth.fullName'], { exact: true }).fill('Çağrı Öğrenci');
  await page.getByLabel(tr['auth.email'], { exact: true }).fill('sample@example.com');
  await page.getByLabel(tr['auth.password'], { exact: true }).fill('sample-only');
  await page.getByRole('button', { name: tr['auth.createAccount'], exact: true }).click();
  await expect(page.getByRole('status')).toHaveText(labelsTr.sampleValid);
  expect(posts).toEqual([]);
});

test('reduced-motion stops continuous effects and replays while preserving final values', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/app/review/motion');
  expect(await page.locator('.loader-rotation').evaluate(e => getComputedStyle(e).animationName)).toBe('none');
  await page.getByRole('button', { name: labelsEn.replay, exact: true }).click();
  expect(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length)).toBe(0);
  await expect(page.getByRole('progressbar', { name: labelsEn.score, exact: true })).toHaveAttribute('aria-valuenow', '86');
});

test('motion overview accessibility in light and dark mode', async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark']) {
    await preferences(context, 'en', theme); await page.goto('/app/review/motion');
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})));
    });
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  }
});
