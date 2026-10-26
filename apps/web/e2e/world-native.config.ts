/** Explicit service qualification, separate from the hermetic PR smoke suite. */
import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const baseURL = process.env.E2E_WORLD_NATIVE_URL;
if (!baseURL) throw new Error('E2E_WORLD_NATIVE_URL must name the disposable world preview');
const target = new URL(baseURL);
if (
  target.protocol !== 'http:' ||
  ![
    '127.0.0.1',
    '127.0.0.2',
    '127.0.0.3',
    '127.0.0.4',
    '127.0.0.5',
    '127.0.0.6',
    '127.0.0.7',
    '127.0.0.8',
    'localhost',
    'lia-world-native-web',
    'lia-world-home-candidate',
    'lia-world-functions-candidate',
    'lia-world-social-candidate',
    'lia-world-polish-candidate',
    'lia-world-final-candidate',
    'lia-world-final-production',
    'lia-world-qualification-web',
    'lia-world-qualification-production',
    'lia-world-qualification-scroll',
  ].includes(target.hostname) ||
  target.username ||
  target.password ||
  target.pathname !== '/'
)
  throw new Error('Native world proof only accepts an isolated local HTTP preview');
export default defineConfig({
  globalSetup: './native/ready.ts',
  testDir: './native',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  outputDir: resolve(__dirname, '../../../.tmp/world-native-results'),
  timeout: 120000,
  expect: { timeout: 15000 },
  reporter: [
    ['list'],
    [
      'json',
      {
        outputFile:
          process.env.WORLD_NATIVE_REPORT ??
          resolve(__dirname, '../../../.tmp/world-native-report.json'),
      },
    ],
  ],
  use: {
    baseURL,
    actionTimeout: 15000,
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chromium' } },
    ...(process.env.E2E_ALL_BROWSERS === '1'
      ? [
          { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
          { name: 'webkit', use: { ...devices['Desktop Safari'] } },
        ]
      : []),
  ],
});
