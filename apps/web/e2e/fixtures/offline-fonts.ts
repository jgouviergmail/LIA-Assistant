/** Serve the app's real Material Symbols face without contacting Google Fonts. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';

export const MATERIAL_SYMBOLS_STYLESHEET_URL =
  'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap';
export const MATERIAL_SYMBOLS_FONT_URL =
  'https://fonts.gstatic.com/lia-e2e/MaterialSymbolsOutlined.woff2';
const stylesheet = readFileSync(join(__dirname, 'fonts/material-symbols.css'), 'utf8');
const font = readFileSync(join(__dirname, 'fonts/MaterialSymbolsOutlined.woff2'));

export async function installOfflineFonts(page: Page): Promise<void> {
  const headers = { 'Access-Control-Allow-Origin': '*' };
  await page.route(MATERIAL_SYMBOLS_STYLESHEET_URL, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({ contentType: 'text/css', body: stylesheet, headers });
  });
  await page.route(MATERIAL_SYMBOLS_FONT_URL, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({ contentType: 'font/woff2', body: font, headers });
  });
}
