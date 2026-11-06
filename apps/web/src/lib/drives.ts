/**
 * A drive's brand name, from the connector type the API sends. It reads the same in every
 * language.
 */
const DRIVE_NAMES: Readonly<Record<string, string>> = {
  google_drive: 'Google Drive',
  microsoft_onedrive: 'OneDrive',
};

export function driveName(provider: string): string {
  return DRIVE_NAMES[provider] ?? provider;
}
