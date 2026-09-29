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

test('filters tickets by category and sorts by creation date', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }),
    });
  });

  const mockTickets = [
    {
      id: 1,
      ticket_number: 'TCKT-TECH',
      subject: 'Server connection timeout',
      requester_email: 'dev@example.com',
      status: 'open',
      priority: 'high',
      category: 'technical',
      created_at: '2026-01-01T10:00:00Z',
    },
    {
      id: 2,
      ticket_number: 'TCKT-REFUND',
      subject: 'Refund unwanted renewal',
      requester_email: 'buyer@example.com',
      status: 'open',
      priority: 'medium',
      category: 'refund',
      created_at: '2026-01-02T10:00:00Z',
    },
  ];

  await page.route('**/api/tickets/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockTickets),
    });
  });

  await page.goto('/');
  await expect(page.getByText('TCKT-TECH')).toBeVisible();
  await expect(page.getByText('TCKT-REFUND')).toBeVisible();

  // Filter by category: Technical
  await page.getByRole('button', { name: 'Technical' }).click();
  await expect(page.getByText('TCKT-TECH')).toBeVisible();
  await expect(page.getByText('TCKT-REFUND')).not.toBeVisible();

  // Filter by category: Refund
  await page.getByRole('button', { name: 'Refund' }).click();
  await expect(page.getByText('TCKT-REFUND')).toBeVisible();
  await expect(page.getByText('TCKT-TECH')).not.toBeVisible();

  // Reset to All Categories
  await page.getByRole('button', { name: 'All Categories' }).click();
  await expect(page.getByText('TCKT-TECH')).toBeVisible();
  await expect(page.getByText('TCKT-REFUND')).toBeVisible();

  // Toggle sort order
  await expect(page.getByText('Newest first')).toBeVisible();
  await page.getByRole('button', { name: /Newest first/i }).click();
  await expect(page.getByText('Oldest first')).toBeVisible();
});

test('renders the analytics dashboard with metrics and charts', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }),
    });
  });

  await page.route('**/api/analytics/overview*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total_tickets: 42,
        open_tickets: 12,
        resolved_tickets: 28,
        closed_tickets: 2,
        average_first_reply_time_seconds: 900,
        average_first_reply_time_minutes: 15,
        average_first_reply_time_formatted: '15m',
        ai_suggestions: {
          total: 20,
          accepted: 16,
          pending: 4,
          acceptance_rate: 80.0,
        },
        tickets_per_day: [
          { date: '2026-09-20', count: 4 },
          { date: '2026-09-21', count: 6 },
          { date: '2026-09-22', count: 8 },
        ],
        categories: [
          { category: 'general', label: 'General', count: 18 },
          { category: 'technical', label: 'Technical', count: 14 },
          { category: 'refund', label: 'Refund', count: 10 },
        ],
        priorities: [
          { priority: 'high', count: 10 },
          { priority: 'medium', count: 22 },
          { priority: 'low', count: 10 },
        ],
      }),
    });
  });

  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Support & AI Analytics Dashboard' })).toBeVisible();
  await expect(page.getByText('42', { exact: true })).toBeVisible();
  await expect(page.getByText('15m', { exact: true })).toBeVisible();
  await expect(page.getByText('80%', { exact: true })).toBeVisible();
  await expect(page.getByText('Tickets per Day')).toBeVisible();
  await expect(page.getByText('Tickets by Category')).toBeVisible();
  await expect(page.getByText('Tickets by Priority')).toBeVisible();
});
