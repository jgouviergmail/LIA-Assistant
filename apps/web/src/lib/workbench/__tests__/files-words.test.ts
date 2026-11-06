/**
 * The Files tool names the drive the account has (ADR-369, lot 6): a word that names a
 * place or a brand is OneDrive's own there, and every other is shared.
 */

import { describe, expect, it } from 'vitest';

import { fileWord } from '../files-words';

describe('fileWord', () => {
  it('keeps Drive’s word on Drive, and when nobody says', () => {
    expect(fileWord('google_drive', 'my_drive')).toBe('workbench.files.my_drive');
    expect(fileWord(null, 'my_drive')).toBe('workbench.files.my_drive');
    expect(fileWord(undefined, 'open_in_drive')).toBe('workbench.files.open_in_drive');
  });

  it('gives OneDrive its own word for what names the drive', () => {
    expect(fileWord('microsoft_onedrive', 'my_drive')).toBe('workbench.files.onedrive.my_drive');
    expect(fileWord('microsoft_onedrive', 'open_in_drive')).toBe(
      'workbench.files.onedrive.open_in_drive'
    );
  });

  it('shares the words that name nothing', () => {
    expect(fileWord('microsoft_onedrive', 'no_name')).toBe('workbench.files.no_name');
  });
});
