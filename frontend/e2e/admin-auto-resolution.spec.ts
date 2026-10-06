import { expect, test } from '@playwright/test';

test('administrator updates database-backed AI auto-resolution settings', async ({ page }) => {
  const admin = {
    id: 1,
    username: 'admin-settings',
    email: 'admin@example.com',
    role: 'ADMIN',
  };
  let settings = {
    enabled: false,
    email_auto_reply: true,
    whatsapp_auto_reply: false,
    simulation_mode: true,
    minimum_threshold: 0.85,
    changed_at: '2026-10-06T10:00:00Z',
    changed_by: null as string | null,
    stats: {
      auto_resolved_today: 1,
      auto_resolved_this_week: 4,
      sent_successfully: 8,
      sent_failed: 1,
      sent_to_agent_review: 3,
    },
  };
  let savedSettings: typeof settings | null = null;
  const patchRequests: Array<{ pathname: string; method: string; body: Record<string, unknown> }> = [];
  const settingsResponseStatuses: number[] = [];

  page.on('response', (response) => {
    if (new URL(response.url()).pathname === '/api/admin/auto-resolution/') {
      settingsResponseStatuses.push(response.status());
    }
  });
  await page.addInitScript(() => {
    window.sessionStorage.setItem('helpdesk-auth-token', 'admin-tab-token');
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (pathname === '/api/auth/csrf/') {
      await route.fulfill({ status: 200, json: { csrfToken: 'csrf-token' } });
      return;
    }
    if (pathname === '/api/auth/token-login/') {
      await route.fulfill({ status: 200, json: { token: 'admin-tab-token', user: admin } });
      return;
    }
    if (pathname === '/api/auth/me/') {
      await route.fulfill({ status: 200, json: admin });
      return;
    }
    if (pathname === '/api/agents/') {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (pathname === '/api/admin/auto-resolution/') {
      if (request.method() === 'PATCH') {
        const body = request.postDataJSON() as Record<string, unknown>;
        patchRequests.push({ pathname, method: request.method(), body });
        savedSettings = { ...settings, ...body, changed_by: admin.username };
        settings = savedSettings;
      }
      await route.fulfill({ status: 200, json: settings });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: 'Not found' } });
  });

  await page.goto('/admin/agents');

  await expect(page.getByRole('heading', { name: 'AI Auto-Resolution' })).toBeVisible();
  await expect(page.getByText('Auto-resolved today')).toBeVisible();
  await page.getByLabel('AI Auto-Resolution master switch').check();

  await expect.poll(() => savedSettings?.enabled).toBe(true);
  expect(settingsResponseStatuses.at(-1)).toBe(200);
  expect(patchRequests.at(-1)).toEqual({
    pathname: '/api/admin/auto-resolution/',
    method: 'PATCH',
    body: { enabled: true },
  });
  await expect(page.getByText('Runtime status: ON')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Runtime status: ON')).toBeVisible();

  await page.getByLabel('AI Auto-Resolution master switch').uncheck();
  await expect.poll(() => savedSettings?.enabled).toBe(false);
  expect(settingsResponseStatuses.at(-1)).toBe(200);
  expect(patchRequests.at(-1)?.body).toEqual({ enabled: false });
  await expect(page.getByText('Runtime status: OFF')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Runtime status: OFF')).toBeVisible();

  await page.getByLabel('AI Auto-Resolution master switch').check();
  await page.getByLabel('WhatsApp Auto-Reply').check();
  await page.getByLabel('Minimum similarity / confidence').fill('90');
  await page.getByRole('button', { name: 'Save settings' }).click();

  await expect.poll(() => savedSettings?.enabled).toBe(true);
  expect(savedSettings?.whatsapp_auto_reply).toBe(true);
  expect(savedSettings?.minimum_threshold).toBe(0.9);
  await expect(page.getByText('ON', { exact: true })).toBeVisible();
});
