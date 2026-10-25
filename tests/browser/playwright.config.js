import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  outputDir: '../../.cache/browser-results',
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 15000,
  reporter: 'list',
  use: {headless: true, viewport: {width: 1440, height: 900}, timezoneId: 'Asia/Tokyo', locale: 'fr-FR'}
});
