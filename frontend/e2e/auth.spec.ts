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
      if (request.url().endsWith('/api/auth/login/')) {
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
    await expect(page.getByRole('heading', { name: `Welcome back, ${credentials.username}` })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
  });

  test('accepts an email address and persists the session after reload', async ({ page }) => {
    await page.getByLabel('Email or username').fill(credentials.email);
    await page.getByLabel('Password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/$/);

    await page.reload();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(credentials.username, { exact: true })).toBeVisible();
  });

  test('masks the password and disables the submit button while signing in', async ({ page }) => {
    await page.getByLabel('Password').fill(credentials.password);
    await expect(page.getByLabel('Password')).toHaveAttribute('type', 'password');

    await page.route('**/api/auth/csrf/', async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify({ csrfToken: 'csrf-token' }) });
    });
    await page.route('**/api/auth/login/', async (route) => {
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
    await page.route('**/api/auth/login/', async (route) => {
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

    await page.getByRole('button', { name: 'Sign Out' }).click();

    await expect(page).toHaveURL(/\/login$/);
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });
});
