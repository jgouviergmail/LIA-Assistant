/**
 * The words of the Files tool that name the drive (ADR-369, lot 6).
 *
 * Google Drive and OneDrive share a screen and most of its words; these name a place or
 * a brand, and OneDrive has its own.
 */
const NAMED: ReadonlySet<string> = new Set([
  'search_label',
  'results',
  'my_drive',
  'shared_drives',
  'open_in_drive',
  'too_large',
  'drive_only',
  'trash_description',
  'outside_my_drive',
]);

/**
 * @param provider - The connector serving the tool.
 * @param word - A key of `workbench.files`.
 * @returns The key to translate.
 */
export function fileWord(provider: string | null | undefined, word: string): string {
  const own = provider === 'microsoft_onedrive' && NAMED.has(word);
  return `workbench.files.${own ? 'onedrive.' : ''}${word}`;
}
