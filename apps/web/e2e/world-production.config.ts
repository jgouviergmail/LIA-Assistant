/** Same native safety gates, against an optimized local build and the real menu. */
import { defineConfig } from '@playwright/test';
import native from './world-native.config';

export default defineConfig({ ...native, testDir: './production', timeout: 180000 });
