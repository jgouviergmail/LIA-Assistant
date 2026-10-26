/** Real upload and native import dialog, retained inside the embedded world host. */
import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { SIZE, meetingImportRoutes, voiceMemo } from '../fixtures/meeting-import';
import { WORLD } from '../../src/features/world/definition';
import fr from '../../locales/fr/translation.json';

for (const [device, viewport] of [
  ['desktop', { width: 1440, height: 900 }],
  ['phone', { width: 390, height: 844 }],
] as const) {
  test(
    'world meeting import retains host navigation and close/reopen list (' + device + ')',
    async ({ page, authenticate, mockApi }, info) => {
      await page.setViewportSize(viewport);
      const owner = await authenticate({ language: 'fr' });
      const room = WORLD.zones.find(zone => zone.id === 'meeting');
      const table = WORLD.props.find(prop => prop.key === 'meetings');
      if (!room || !table) throw new Error('Missing authored meeting workspace');
      const sent: number[] = [],
        opened: unknown[] = [],
        completed: unknown[] = [];
      await installInertWorldAdmission(page, owner.id, { spawn: room.arrival });
      await mockApi(meetingImportRoutes(sent, opened, completed, true));
      await page.goto('/fr/dashboard/world');
      await enterWorld(page);
      await expect(page.locator('[data-world-status="shared"]')).toBeVisible();
      const hostUrl = page.url();
      const point = await frameWorldProp(
        page,
        table,
        id => fr.world.zones[id as keyof typeof fr.world.zones]
      );
      await page.mouse.click(point.x, point.y);
      const workspace = page
        .getByRole('dialog')
        .filter({ has: page.getByRole('heading', { name: fr.meetings.list.title, exact: true, level: 1 }) });
      await expect(workspace).toBeVisible();
      await workspace.getByRole('button', { name: 'Importer', exact: true }).click();
      const upload = page.getByRole('dialog', { name: 'Importer un enregistrement' });
      await upload.getByLabel('Fichier audio').setInputFiles({
        name: 'world-memo.m4a',
        mimeType: 'audio/mp4',
        buffer: voiceMemo(),
      });
      await upload.getByRole('button', { name: 'Importer', exact: true }).click();
      await expect(page.getByText('Importé', { exact: true })).toBeVisible();
      await expect(page).toHaveURL(hostUrl);
      expect(opened).toEqual([
        expect.objectContaining({ size_bytes: SIZE, audio_format: 'import_m4a' }),
      ]);
      expect(sent).toEqual([0, 1, 2]);
      expect(completed).toEqual([{ chunk_count: 3 }]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
      await page.screenshot({ path: info.outputPath('world-import-' + device + '.png') });
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      const again = await frameWorldProp(
        page,
        table,
        id => fr.world.zones[id as keyof typeof fr.world.zones]
      );
      await page.mouse.click(again.x, again.y);
      await expect(
        page.getByRole('heading', { name: fr.meetings.list.title, exact: true, level: 1 })
      ).toBeVisible();
      await expect(page.getByText('Importé', { exact: true })).toHaveCount(0);
    }
  );
}
