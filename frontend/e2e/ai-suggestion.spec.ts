import { expect, test } from '@playwright/test';

test('generates, edits, and accepts an AI suggested reply', async ({ page }) => {
  let suggestionAccepted = false;

  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', email: 'agent@example.com', role: 'AGENT' }),
    });
  });
  await page.route('**/api/tickets/1/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        ticket_number: 'TCKT-001',
        subject: 'Password reset',
        requester_email: 'customer@example.com',
        status: 'open',
        category: 'technical',
        priority: 'medium',
        created_at: '2026-01-01T00:00:00Z',
      }),
    });
  });
  await page.route('**/api/tickets/1/messages/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, body: 'I cannot sign in.', message_type: 'customer', created_at: '2026-01-01T00:00:00Z' }]),
    });
  });
  await page.route('**/api/auth/csrf/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrfToken: 'csrf' }) });
  });
  await page.route('**/api/tickets/1/suggest-reply/', async (route) => {
    await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ task_id: 'task-1' }) });
  });
  await page.route('**/api/tickets/1/suggestion-status/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 4,
        status: 'succeeded',
        message: {
          id: 2,
          body: 'Please use the password reset link to regain access.',
          message_type: 'agent',
          is_ai_generated: true,
          is_draft: true,
          created_at: '2026-01-01T00:00:00Z',
        },
      }),
    });
  });
  await page.route('**/api/tickets/1/accept-suggestion/', async (route) => {
    suggestionAccepted = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 2,
        body: 'Please use the password reset link to regain access. Let us know if you need help.',
        message_type: 'agent',
        is_ai_generated: false,
        is_draft: false,
        created_at: '2026-01-01T00:00:00Z',
      }),
    });
  });

  await page.goto('/tickets/1');
  await expect(page.getByRole('heading', { name: 'Password reset' })).toBeVisible();
  await page.getByRole('button', { name: 'Suggest reply with AI' }).click();
  await expect(page.getByLabel('Edit AI suggested reply')).toHaveValue(
    'Please use the password reset link to regain access.',
  );
  await page.getByLabel('Edit AI suggested reply').fill(
    'Please use the password reset link to regain access. Let us know if you need help.',
  );
  await page.getByRole('button', { name: 'Accept suggestion' }).click();

  await expect(page.getByText('AI suggested reply')).not.toBeVisible();
  await expect(page.getByText('Please use the password reset link to regain access. Let us know if you need help.')).toBeVisible();
  expect(suggestionAccepted).toBe(true);
});
