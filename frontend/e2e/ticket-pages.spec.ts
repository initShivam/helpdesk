import { expect, test } from '@playwright/test';

test('renders the ticket list from the API and opens ticket detail', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }),
    });
  });
  await page.route('**/api/tickets/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 1,
          ticket_number: 'TCKT-001',
          subject: 'Printer issue',
          requester_email: 'customer@example.com',
          status: 'open',
          priority: 'high',
          category: 'technical',
          created_at: '2026-01-01T00:00:00Z',
        },
      ]),
    });
  });
  await page.route('**/api/tickets/1/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        ticket_number: 'TCKT-001',
        subject: 'Printer issue',
        requester_email: 'customer@example.com',
        description: 'Printer is offline.',
        status: 'open',
        priority: 'high',
        category: 'technical',
        created_at: '2026-01-01T00:00:00Z',
        attachments: [],
      }),
    });
  });
  await page.route('**/api/tickets/1/messages/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.goto('/');
  await expect(page.getByText('TCKT-001', { exact: true })).toBeVisible();
  await expect(page.getByText('Printer issue', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'TCKT-001' }).click();

  await expect(page).toHaveURL(/\/tickets\/1$/);
  await expect(page.getByRole('heading', { name: 'Printer issue' })).toBeVisible();
  await expect(page.getByText('technical', { exact: true })).toBeVisible();
});
