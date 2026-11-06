import { test as base, expect, type APIRequestContext } from '@playwright/test';
const test = base.extend({ request: async ({ context }, provide) => { await provide(context.request); } });
const origin = 'http://127.0.0.1:3111';
const fixture = 'http://127.0.0.1:4412';
const api = (r: APIRequestContext, action: string, data: object, requestOrigin = origin) => r.post(origin + '/app/api/auth/' + action, { data, headers: { Origin: requestOrigin } });
const state = async (r: APIRequestContext) => (await r.get(fixture + '/__fixture/state')).json();
const signin = (r: APIRequestContext, email = 'student@example.test') => api(r, 'signin', { email, password: 'valid-password' });
test.beforeEach(async ({ request }) => { await request.post(fixture + '/__fixture/reset'); });

test('verified student session uses private HttpOnly cookies and exposes no identity data', async ({ request, context, page }) => {
  const login = await signin(request); expect(login.status()).toBe(200); expect((await login.json()).destination).toBe('/app/student');
  const response = await request.get('/app/api/session'); expect(response.headers()['cache-control']).toContain('no-store');
  expect(await response.json()).toEqual({ authenticated: true, role: 'intern', destination: '/app/student' });
  const cookies = (await context.cookies()).filter(c => c.name.startsWith('im-web-session')); expect(cookies.length).toBeGreaterThan(0);
  for (const cookie of cookies) { expect(cookie.httpOnly).toBe(true); expect(cookie.path).toBe('/app'); expect(cookie.sameSite).toBe('Lax'); }
  await page.goto('/app/student'); await expect(page.getByTestId('student-workspace')).toBeVisible();
});
test('employer cannot render student workspace', async ({ request, page }) => {
  expect((await signin(request, 'boss@example.test')).status()).toBe(200); await page.goto('/app/student'); await expect(page).toHaveURL(/\/app\/employer$/);
});
test('invalid password does not create a session', async ({ request }) => {
  expect((await api(request, 'signin', { email: 'student@example.test', password: 'wrong' })).status()).toBe(401);
  expect((await (await request.get('/app/api/session')).json()).authenticated).toBe(false);
});
test('unknown canonical role never defaults to student', async ({ request }) => {
  const response = await signin(request, 'unknown@example.test'); expect(response.status()).toBe(409); expect((await response.json()).code).toBe('roleUnavailable');
});
test('orphan email identity cannot become an implicit account', async ({ request }) => {
  expect((await signin(request, 'orphan@example.test')).status()).toBe(403);
  expect((await state(request)).events.filter((e: { path: string }) => e.path === '/auth/complete-signup')).toHaveLength(0);
});
test('confirmed email signup intent provisions via dedicated backend endpoint', async ({ request }) => {
  expect((await signin(request, 'pending@example.test')).status()).toBe(200);
  const events = (await state(request)).events.filter((e: { path: string }) => e.path === '/auth/complete-signup');
  expect(events).toHaveLength(1); expect(events[0].body.account_type).toBe('intern');
});
test('signup requires explicit role before contacting Supabase', async ({ request }) => {
  const response = await api(request, 'signup', { fullName: 'Example', email: 'new@example.test', password: 'valid-password' }); expect(response.status()).toBe(400);
  expect((await state(request)).events).toHaveLength(0);
});
test('signup confirmation exchanges PKCE then creates canonical employer profile', async ({ request }) => {
  const response = await api(request, 'signup', { role: 'employer', fullName: 'Çağrı الطالب', email: 'new@example.test', password: 'valid-password' }); expect(response.status()).toBe(200);
  let snapshot = await state(request); expect(snapshot.users.find((u: { email: string }) => u.email === 'new@example.test').profile).toBe(false);
  const callback = await request.get('/app/api/auth/callback?code=' + snapshot.codes[0].code, { maxRedirects: 0 });
  expect(callback.headers().location).toBe(origin + '/app/employer');
  snapshot = await state(request); expect(snapshot.events.some((e: { grant: string; hasVerifier: boolean }) => e.grant === 'pkce' && e.hasVerifier)).toBe(true);
});
test('invalid callback cannot log out an existing valid account', async ({ request }) => {
  await signin(request); await request.get('/app/api/auth/callback?code=forged', { maxRedirects: 0 });
  expect((await (await request.get('/app/api/session')).json()).authenticated).toBe(true);
});
test('recovery requires email callback and token-bound grant', async ({ request }) => {
  expect((await api(request, 'recover', { email: 'student@example.test' })).status()).toBe(200);
  const code = (await state(request)).codes[0].code;
  const callback = await request.get('/app/api/auth/callback?code=' + code, { maxRedirects: 0 }); expect(callback.headers().location).toBe(origin + '/app/reset-password');
  expect((await api(request, 'reset', { password: 'changed-password' })).status()).toBe(200);
  expect((await api(request, 'signin', { email: 'student@example.test', password: 'changed-password' })).status()).toBe(200);
});
test('ordinary authenticated session cannot reset without recovery grant', async ({ request }) => {
  await signin(request); expect((await api(request, 'reset', { password: 'changed-password' })).status()).toBe(403);
});
test('cross-origin mutations are rejected', async ({ request }) => {
  expect((await api(request, 'signin', { email: 'student@example.test', password: 'valid-password' }, 'https://attacker.example')).status()).toBe(403);
});
test('backend outage preserves session and permits retry', async ({ request }) => {
  await signin(request); await request.post(fixture + '/__fixture/control', { data: { failBackend: true } });
  expect((await request.get('/app/api/session')).status()).toBe(503);
  await request.post(fixture + '/__fixture/control', { data: { failBackend: false } });
  expect((await (await request.get('/app/api/session')).json()).authenticated).toBe(true);
});
test('logout clears local access and protects account pages', async ({ request, page }) => {
  await signin(request); expect((await api(request, 'logout', {})).status()).toBe(200);
  expect((await (await request.get('/app/api/session')).json()).authenticated).toBe(false);
  await page.goto('/app/student'); await expect(page).toHaveURL(/\/app\/sign-in$/);
});
test('Google signup accepts provider identity with explicit role', async ({ request }) => {
  const response = await api(request, 'oauth', { provider: 'google', mode: 'signup', role: 'intern' }); expect(response.status()).toBe(200);
  await request.get((await response.json()).oauthUrl);
  const snapshot = await state(request); expect(snapshot.users.find((u: { email: string }) => u.email === 'social-new@example.test').role).toBe('intern');
});
test('Google sign-in cleans up new identity without provisioning an account', async ({ request }) => {
  const response = await api(request, 'oauth', { provider: 'google', mode: 'signin' }); await request.get((await response.json()).oauthUrl);
  const snapshot = await state(request); expect(snapshot.users.some((u: { email: string }) => u.email === 'social-new@example.test')).toBe(false);
  expect(snapshot.events.some((e: { path: string }) => e.path === '/auth/complete-signup')).toBe(false);
});
test('social signup never repurposes or deletes an existing canonical account', async ({ request }) => {
  await request.post(fixture + '/__fixture/control', { data: { social: 'boss@example.test' } });
  const response = await api(request, 'oauth', { provider: 'google', mode: 'signup', role: 'intern' }); await request.get((await response.json()).oauthUrl);
  const snapshot = await state(request); expect(snapshot.users.find((u: { email: string }) => u.email === 'boss@example.test').role).toBe('employer');
  expect(snapshot.events.some((e: { path: string }) => ['/auth/complete-signup', '/auth/account'].includes(e.path))).toBe(false);
});
test('Apple remains disabled until web integration is implemented', async ({ request }) => {
  expect((await api(request, 'oauth', { provider: 'apple', mode: 'signin' })).status()).toBe(503);
});

test('real browser form signs in and reaches canonical workspace', async ({ page }) => {
  await page.goto('/app/sign-in'); await page.locator('#auth-email').fill('student@example.test'); await page.locator('#auth-password').fill('valid-password');
  await page.locator('form button[type="submit"]').click(); await expect(page).toHaveURL(/\/app\/student$/);
});
test('signup locked fields guide the user to role selection', async ({ page }) => {
  await page.goto('/app/sign-up'); await expect(page.locator('#auth-email')).toBeDisabled(); await page.locator('.role-lock-overlay').first().click();
  await expect(page.locator('input[name="role"]').first()).toBeFocused(); await page.locator('input[name="role"][value="intern"]').check();
  await expect(page.locator('#auth-email')).toBeEnabled();
});
test('tampered recovery intent cannot update password', async ({ request, context }) => {
  await api(request, 'recover', { email: 'student@example.test' }); const code = (await state(request)).codes[0].code;
  await context.addCookies([{ name: 'im-web-flow', value: 'forged', domain: '127.0.0.1', path: '/app' }]);
  await request.get('/app/api/auth/callback?code=' + code, { maxRedirects: 0 }); expect((await api(request, 'reset', { password: 'changed-password' })).status()).toBe(403);
  expect((await state(request)).events.some((e: { path: string }) => e.path === 'password-update')).toBe(false);
});
for (const locale of ['en', 'tr', 'ar']) for (const theme of ['light', 'dark']) {
  test(`${locale} ${theme}: real auth is accessible at 320px without overflow`, async ({ page, context }) => {
    await context.addCookies([{ name: 'im-web-locale', value: locale, domain: '127.0.0.1', path: '/app' }, { name: 'im-web-appearance', value: theme, domain: '127.0.0.1', path: '/app' }]);
    await page.setViewportSize({ width: 320, height: 900 }); await page.goto('/app/sign-up');
    expect(await page.locator('html').getAttribute('dir')).toBe(locale === 'ar' ? 'rtl' : 'ltr');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const { default: AxeBuilder } = await import('@axe-core/playwright');
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    if (locale === 'ar' && theme === 'dark') await page.screenshot({ path: test.info().outputPath('auth-ar-dark.png'), fullPage: true });
  });
}
test('independent browser contexts never share account sessions', async ({ browser, request }) => {
  await signin(request); const other = await browser.newContext();
  try { expect((await (await other.request.get(origin + '/app/api/session')).json()).authenticated).toBe(false); } finally { await other.close(); }
});
test('root and anonymous protected routes preserve base path exactly once', async ({ page }) => {
  await page.goto('/app'); await expect(page).toHaveURL(origin + '/app/sign-in');
});
test('expired access token refreshes using browser-bound refresh cookie', async ({ request }) => {
  await request.post(fixture + '/__fixture/control', { data: { nextExpiry: -1 } });
  expect((await signin(request)).status()).toBe(200);
  expect((await (await request.get('/app/api/session')).json()).authenticated).toBe(true);
  expect((await state(request)).events.some((e: { grant: string }) => e.grant === 'refresh_token')).toBe(true);
});
