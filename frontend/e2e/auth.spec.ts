import { expect, test } from '@playwright/test';

const credentials = {
  username: 'e2e-user',
  email: 'e2e-user@example.com',
  password: 'E2ePass123!',
};

test.describe('authentication', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('Welcome back', { exact: true })).toBeVisible();
  });

  test('redirects unauthenticated users from protected routes to login', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel('Email or username')).toBeVisible();
  });

  test('shows browser validation and does not submit empty credentials', async ({ page }) => {
    let loginRequests = 0;
    await page.on('request', (request) => {
      if (request.url().endsWith('/api/auth/token-login/')) {
        loginRequests += 1;
      }
    });

    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByLabel('Email or username')).toBeFocused();
    await expect(page.getByLabel('Email or username')).toHaveJSProperty('validity.valid', false);
    await expect(page.getByLabel('Password')).toHaveJSProperty('validity.valid', false);
    expect(loginRequests).toBe(0);
  });

  test('rejects an incorrect password without creating a session', async ({ page, context }) => {
    await page.getByLabel('Email or username').fill(credentials.username);
    await page.getByLabel('Password').fill('WrongPassword!');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toContainText('Invalid credentials');
    await expect(page).toHaveURL(/\/login$/);
    expect((await context.cookies()).some((cookie) => cookie.name === 'sessionid')).toBe(false);
  });

  test('accepts a username with surrounding whitespace', async ({ page }) => {
    await page.getByLabel('Email or username').fill(`  ${credentials.username}  `);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), e2e-user/ })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expect(page.evaluate(() => sessionStorage.getItem('helpdesk-auth-token'))).resolves.toBeTruthy();
    await expect(page.evaluate(() => localStorage.getItem('helpdesk-auth-token'))).resolves.toBeNull();
  });

  test('accepts an email address and persists the tab credential after reload', async ({ page }) => {
    await page.getByLabel('Email or username').fill(credentials.email);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/$/);
    const token = await page.evaluate(() => sessionStorage.getItem('helpdesk-auth-token'));
    expect(token).toBeTruthy();
    await expect(page.evaluate(() => localStorage.getItem('helpdesk-auth-token'))).resolves.toBeNull();

    await page.reload();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(credentials.username, { exact: true })).toBeVisible();
    await expect(page.evaluate(() => sessionStorage.getItem('helpdesk-auth-token'))).resolves.toBe(token);
  });

  test('masks the password and disables the submit button while signing in', async ({ page }) => {
    await page.getByLabel('Password').fill(credentials.password);
    await expect(page.getByLabel('Password')).toHaveAttribute('type', 'password');

    await page.route('**/api/auth/csrf/', async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify({ csrfToken: 'csrf-token' }) });
    });
    await page.route('**/api/auth/token-login/', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 250));
      await route.fulfill({ status: 401, body: JSON.stringify({ detail: 'Invalid credentials' }) });
    });

    await page.getByLabel('Email or username').fill(credentials.username);
    const submit = page.getByRole('button', { name: 'Sign in' });
    await submit.click();
    await expect(page.getByRole('button', { name: 'Signing in...' })).toBeDisabled();
    await expect(page.getByRole('alert')).toContainText('Invalid credentials');
  });

  test('surfaces a CSRF initialization failure', async ({ page }) => {
    await page.route('**/api/auth/csrf/', async (route) => {
      await route.fulfill({ status: 503, body: 'service unavailable' });
    });

    await page.getByLabel('Email or username').fill(credentials.username);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toContainText('Unable to initialize secure login');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('handles a non-JSON login error response', async ({ page }) => {
    await page.route('**/api/auth/csrf/', async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify({ csrfToken: 'csrf-token' }) });
    });
    await page.route('**/api/auth/token-login/', async (route) => {
      await route.fulfill({ status: 500, body: 'Authentication service unavailable' });
    });

    await page.getByLabel('Email or username').fill(credentials.username);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toContainText('Authentication service unavailable');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('logs out and prevents access to the protected page', async ({ page }) => {
    await page.getByLabel('Email or username').fill(credentials.username);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/$/);

    await page.getByRole('button', { name: 'Sign out' }).click();

    await expect(page).toHaveURL(/\/login$/);
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('keeps identities and logout isolated between tabs', async ({ page, context }) => {
    const users = {
      admin: { id: 1, username: 'admin-tab', email: 'admin@example.com', role: 'ADMIN' },
      agent: { id: 2, username: 'agent-tab', email: 'agent@example.com', role: 'AGENT' },
    };
    const credentialsByToken = new Map<string, typeof users.admin>();
    const revokedTokens = new Set<string>();

    await context.route('**/api/**', async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === '/api/auth/csrf/') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ csrfToken: 'csrf-token' }),
        });
        return;
      }
      if (pathname === '/api/auth/token-login/') {
        const body = JSON.parse(route.request().postData() || '{}') as { username: string };
        const user = body.username === 'admin' ? users.admin : users.agent;
        const token = `${body.username}-tab-token`;
        credentialsByToken.set(token, user);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ token, user }),
        });
        return;
      }

      const authorization = route.request().headers().authorization;
      const token = authorization?.replace(/^Bearer /, '');
      const user = token ? credentialsByToken.get(token) : undefined;
      if (pathname === '/api/auth/me/') {
        await route.fulfill({
          status: user && !revokedTokens.has(token ?? '') ? 200 : 401,
          contentType: 'application/json',
          body: JSON.stringify(user ?? { detail: 'Invalid credential' }),
        });
        return;
      }
      if (pathname === '/api/auth/logout/') {
        if (token) revokedTokens.add(token);
        await route.fulfill({ status: 200 });
        return;
      }
      await route.fulfill({
        status: user && !revokedTokens.has(token ?? '') ? 200 : 401,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 0,
          results: [],
          next: null,
          previous: null,
          stats: { total: 0, open: 0, high_urgent: 0, resolved: 0 },
        }),
      });
    });

    const loginAs = async (target: typeof page, username: 'admin' | 'agent') => {
      await target.goto('/login');
      await target.getByLabel('Email or username').fill(username);
      await target.getByLabel('Password').fill('test-password');
      await target.getByRole('button', { name: 'Sign in' }).click();
      await expect(target).toHaveURL(/\/$/);
      await expect(target.getByText(users[username].username, { exact: true })).toBeVisible();
    };

    await loginAs(page, 'admin');
    const agentPage = await context.newPage();
    await loginAs(agentPage, 'agent');

    await page.reload();
    await expect(page.getByText(users.admin.username, { exact: true })).toBeVisible();
    await agentPage.reload();
    await expect(agentPage.getByText(users.agent.username, { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.evaluate(() => sessionStorage.getItem('helpdesk-auth-token'))).resolves.toBeNull();
    await expect(agentPage.evaluate(() => sessionStorage.getItem('helpdesk-auth-token'))).resolves.toBe('agent-tab-token');
    await agentPage.reload();
    await expect(agentPage.getByText(users.agent.username, { exact: true })).toBeVisible();

    await agentPage.getByRole('button', { name: 'Sign out' }).click();
    await expect(agentPage).toHaveURL(/\/login$/);
    expect([...revokedTokens].sort()).toEqual(['admin-tab-token', 'agent-tab-token']);
  });
});
