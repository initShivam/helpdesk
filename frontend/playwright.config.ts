import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: '../.env' });

const backendPort = 8001;
const frontendPort = 5174;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  outputDir: 'test-results',
  use: {
    baseURL: frontendUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: 'python manage.py migrate --noinput && python manage.py runserver 127.0.0.1:8001',
      cwd: '../backend',
      url: `${backendUrl}/health/`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        HELPDESK_E2E: '1',
        DJANGO_DEBUG: 'True',
        DJANGO_ALLOWED_HOSTS: '127.0.0.1,localhost',
        E2E_POSTGRES_DB: process.env.E2E_POSTGRES_DB || 'helpdesk_e2e',
        E2E_POSTGRES_USER: process.env.E2E_POSTGRES_USER || process.env.POSTGRES_USER || 'postgres',
        E2E_POSTGRES_PASSWORD: process.env.E2E_POSTGRES_PASSWORD || process.env.POSTGRES_PASSWORD || 'postgres',
        E2E_POSTGRES_HOST: process.env.E2E_POSTGRES_HOST || process.env.POSTGRES_HOST || 'localhost',
        E2E_POSTGRES_PORT: process.env.E2E_POSTGRES_PORT || process.env.POSTGRES_PORT || '5432',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174',
      url: frontendUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        VITE_API_PROXY_TARGET: backendUrl,
      },
    },
  ],
});
