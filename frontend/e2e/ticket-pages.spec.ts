import { expect, test } from '@playwright/test';

test('shows a personalized home overview and persists the selected theme', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'alex-agent', role: 'AGENT' }),
    });
  });
  await page.route('**/api/tickets/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        stats: { total: 8, open: 3, high_urgent: 1, resolved: 4 },
        results: [{
          id: 1,
          ticket_number: 'TCKT-HOME',
          subject: 'Welcome ticket',
          requester_email: 'customer@example.com',
          status: 'open',
          priority: 'medium',
          category: 'general',
          created_at: '2026-01-01T00:00:00Z',
        }],
      }),
    });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), alex-agent/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Welcome ticket', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Tickets', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.evaluate(() => localStorage.getItem('helpdesk-theme'))).resolves.toBe('dark');
  await page.reload();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.getByRole('button', { name: 'Switch to light theme' })).toBeVisible();
});

test('keeps Home recent ticket columns aligned and truncates long values', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('pageerror', (error) => browserErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }),
    });
  });
  await page.route('**/api/tickets/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        stats: { total: 1, open: 0, high_urgent: 0, resolved: 1 },
        results: [{
          id: 1,
          ticket_number: 'EMAIL-C36173782F4641',
          subject: 'Confirm your business email address to continue with your support request',
          requester_email: 'initshivam@gmail.com',
          status: 'resolved',
          priority: 'medium',
          category: 'general',
          created_at: '2026-10-05T00:00:00Z',
        }],
      }),
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const table = page.locator('table').first();
  const row = table.getByRole('row').nth(1);
  const cells = row.getByRole('cell');
  const ticketBounds = await cells.nth(0).boundingBox();
  const subjectBounds = await cells.nth(1).boundingBox();
  expect(ticketBounds).not.toBeNull();
  expect(subjectBounds).not.toBeNull();
  expect(ticketBounds!.x + ticketBounds!.width).toBeLessThanOrEqual(subjectBounds!.x + 1);

  const ticketId = cells.nth(0).getByRole('link', { name: 'EMAIL-C36173782F4641' });
  await expect(ticketId).toBeVisible();
  expect(await ticketId.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  await expect(cells.nth(1).getByRole('link', { name: /Confirm your business email/ })).toBeVisible();
  await expect(cells.nth(1).getByText('initshivam@gmail.com')).toBeVisible();
  for (let columnIndex = 2; columnIndex < 6; columnIndex += 1) {
    const headerBounds = await table.getByRole('row').first().getByRole('columnheader').nth(columnIndex).boundingBox();
    const cellBounds = await cells.nth(columnIndex).boundingBox();
    expect(headerBounds).not.toBeNull();
    expect(cellBounds).not.toBeNull();
    expect(Math.abs(headerBounds!.x - cellBounds!.x)).toBeLessThanOrEqual(1);
  }

  for (const width of [1280, 1024, 768]) {
    await page.setViewportSize({ width, height: 900 });
    const currentTicketBounds = await cells.nth(0).boundingBox();
    const currentSubjectBounds = await cells.nth(1).boundingBox();
    expect(currentTicketBounds!.x + currentTicketBounds!.width).toBeLessThanOrEqual(currentSubjectBounds!.x + 1);
  }
  const scroller = table.locator('..');
  expect(await scroller.evaluate((element) => element.scrollWidth > element.clientWidth)).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.md\\:hidden a[href="/tickets/1"]')).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('renders the ticket list from the API and opens ticket detail', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }),
    });
  });
  await page.route('**/api/tickets/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        stats: { total: 1, open: 1, high_urgent: 1, resolved: 0 },
        results: [{
          id: 1,
          ticket_number: 'TCKT-001',
          subject: 'Printer issue',
          requester_email: 'customer@example.com',
          status: 'open',
          priority: 'high',
          category: 'technical',
          created_at: '2026-01-01T00:00:00Z',
        }],
      }),
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
  await page.route('**/api/tickets/1/whatsapp-notifications/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ contact: { number: '', consent: false }, notifications: [] }),
    });
  });

  await page.goto('/tickets');
  await expect(page.getByRole('link', { name: 'TCKT-001', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Printer issue', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'TCKT-001' }).click();

  await expect(page).toHaveURL(/\/tickets\/1$/);
  await expect(page.getByRole('heading', { name: 'Printer issue' })).toBeVisible();
  await expect(page.getByText('technical', { exact: true })).toBeVisible();
});

test('keeps ticket and subject columns separate at desktop widths and scrollable on tablet', async ({ page }) => {
  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }) });
  });
  await page.route('**/api/tickets/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        stats: { total: 1, open: 1, high_urgent: 0, resolved: 0 },
        results: [{
          id: 1,
          ticket_number: 'EMAIL-C36173782F4641',
          subject: 'A very long subject that must truncate rather than overlap other ticket columns',
          requester_email: 'initshivam@example.com',
          status: 'open',
          priority: 'medium',
          category: 'general',
          created_at: '2026-01-01T00:00:00Z',
        }],
      }),
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/tickets');
  const row = page.getByRole('row').nth(1);
  const cells = row.getByRole('cell');
  const ticketBounds = await cells.nth(0).boundingBox();
  const subjectBounds = await cells.nth(1).boundingBox();
  expect(ticketBounds).not.toBeNull();
  expect(subjectBounds).not.toBeNull();
  expect(ticketBounds!.x + ticketBounds!.width).toBeLessThanOrEqual(subjectBounds!.x + 1);
  const desktopTicketId = cells.nth(0).getByRole('link', { name: 'EMAIL-C36173782F4641' });
  await expect(desktopTicketId).toBeVisible();
  expect(await desktopTicketId.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBeTruthy();

  for (const width of [1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    const narrowerTicketBounds = await cells.nth(0).boundingBox();
    const narrowerSubjectBounds = await cells.nth(1).boundingBox();
    expect(narrowerTicketBounds!.x + narrowerTicketBounds!.width).toBeLessThanOrEqual(narrowerSubjectBounds!.x + 1);
  }

  await page.setViewportSize({ width: 768, height: 900 });
  const tableScroller = page.locator('table').locator('..');
  expect(await tableScroller.evaluate((element) => element.scrollWidth > element.clientWidth)).toBeTruthy();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.md\\:hidden a[href="/tickets/1"]')).toBeVisible();
});

test('saves the current WhatsApp contact and keeps notification retry available', async ({ page }) => {
  const browserErrors: string[] = [];
  let savedContact: { number: string; consent: boolean } | null = null;
  let retryRequested = false;
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('helpdesk-theme', 'dark'));

  await page.route('**/api/auth/me/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, username: 'agent', role: 'AGENT' }) });
  });
  await page.route('**/api/auth/csrf/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrfToken: 'csrf' }) });
  });
  await page.route('**/api/tickets/1/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        ticket_number: 'TCKT-WA',
        subject: 'WhatsApp contact test',
        requester_email: 'customer@example.com',
        status: 'open',
        category: 'general',
        priority: 'medium',
        created_at: '2026-01-01T00:00:00Z',
      }),
    });
  });
  await page.route('**/api/tickets/1/messages/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/tickets/1/whatsapp-notifications/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contact: { number: '+919876540331', consent: true },
        notifications: [{
          id: 12,
          status: 'failed',
          attempt_count: 1,
          max_attempts: 3,
          last_attempt_at: '2026-10-05T09:13:27Z',
          delivered_at: null,
          error_code: 'meta_131000',
          error_detail: 'Provider temporarily unavailable.',
        }, {
          id: 13,
          status: 'sent',
          attempt_count: 1,
          max_attempts: 3,
          last_attempt_at: '2026-10-05T09:43:27Z',
          delivered_at: null,
          error_code: '',
          error_detail: '',
        }],
      }),
    });
  });
  await page.route('**/api/tickets/1/whatsapp-contact/', async (route) => {
    savedContact = route.request().postDataJSON() as { number: string; consent: boolean };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ number: savedContact.number, consent: savedContact.consent }) });
  });
  await page.route('**/api/tickets/1/retry-whatsapp-notification/', async (route) => {
    retryRequested = true;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'queued' }) });
  });

  await page.goto('/tickets/1');
  const whatsappPanel = page.locator('[aria-labelledby="whatsapp-heading"]');
  await expect(whatsappPanel.getByRole('heading', { name: 'WhatsApp', exact: true })).toBeVisible();
  expect(await whatsappPanel.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe('rgb(17, 28, 49)');
  for (const width of [1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const panelBounds = await whatsappPanel.boundingBox();
    const inputBounds = await page.getByLabel('WhatsApp number').boundingBox();
    expect(panelBounds).not.toBeNull();
    expect(inputBounds).not.toBeNull();
    expect(panelBounds!.x + panelBounds!.width).toBeLessThanOrEqual(width);
    expect(inputBounds!.x + inputBounds!.width).toBeLessThanOrEqual(width);
  }
  await expect(page.getByText('+919876540331')).toBeVisible();
  const numberInput = page.getByLabel('WhatsApp number');
  await expect(numberInput).toHaveValue('+919876540331');
  expect(await numberInput.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe('rgb(15, 23, 42)');
  const consent = page.getByRole('checkbox', { name: 'Customer consent recorded' });
  await expect(consent).toBeChecked();
  await consent.uncheck();
  await expect(consent).not.toBeChecked();
  await consent.check();
  await page.getByRole('button', { name: 'Save contact' }).click();
  await expect.poll(() => savedContact).toEqual({ number: '+919876540331', consent: true });
  await expect(page.getByText('sent', { exact: true })).toBeVisible();
  await expect(page.getByText(/Delivered /)).toHaveCount(0);
  await expect(page.getByText('Meta WhatsApp error 131000.')).toBeVisible();
  await expect(page.getByText('Provider temporarily unavailable.')).toBeVisible();
  await page.getByRole('button', { name: 'Retry WhatsApp' }).click();
  await expect.poll(() => retryRequested).toBeTruthy();
  expect(browserErrors).toEqual([]);
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

  await page.route('**/api/tickets/**', async (route) => {
    const category = new URL(route.request().url()).searchParams.get('category');
    const results = category
      ? mockTickets.filter((ticket) => ticket.category === category)
      : mockTickets;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: results.length,
        next: null,
        previous: null,
        stats: { total: mockTickets.length, open: 2, high_urgent: 1, resolved: 0 },
        results,
      }),
    });
  });

  await page.goto('/tickets');
  await expect(page.getByRole('link', { name: 'TCKT-TECH', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'TCKT-REFUND', exact: true })).toBeVisible();

  // Filter by category: Technical
  await page.getByLabel('Category').selectOption('technical');
  await expect(page.getByRole('link', { name: 'TCKT-TECH', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'TCKT-REFUND', exact: true })).not.toBeVisible();

  // Filter by category: Refund
  await page.getByLabel('Category').selectOption('refund');
  await expect(page.getByRole('link', { name: 'TCKT-REFUND', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'TCKT-TECH', exact: true })).not.toBeVisible();

  // Reset to All Categories
  await page.getByLabel('Category').selectOption('all');
  await expect(page.getByRole('link', { name: 'TCKT-TECH', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'TCKT-REFUND', exact: true })).toBeVisible();

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
  await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible();
  await expect(page.getByText('42', { exact: true })).toBeVisible();
  await expect(page.getByText('15m', { exact: true })).toBeVisible();
  await expect(page.getByText('80%', { exact: true })).toBeVisible();
  await expect(page.getByText('Tickets per Day')).toBeVisible();
  await expect(page.getByText('Tickets by Category')).toBeVisible();
  await expect(page.getByText('Tickets by Priority')).toBeVisible();
});
