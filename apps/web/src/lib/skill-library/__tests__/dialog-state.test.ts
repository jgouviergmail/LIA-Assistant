/**
 * The skill library dialog's state machine (ADR-327): pure, and every
 * transition named — one request at a time, a refusal kept until the next
 * act, the tabs back under whatever was shown.
 */
import { describe, expect, it } from 'vitest';

import {
  initialLibraryState,
  isLibraryTab,
  libraryDialogReducer,
  type LibraryDialogState,
} from '../dialog-state';
import type { LibraryInstalledItem, LibraryPreview, LibraryUpdatePreview } from '../types';

const PREVIEW: LibraryPreview = {
  portal: 'skills_sh',
  registry_id: 'acme/skills/pdf',
  repository: 'acme/skills',
  ref: 'HEAD',
  path: 'skills/pdf',
  commit_sha: 'a'.repeat(40),
  tree_sha: 'b'.repeat(40),
  name: 'pdf',
  description: 'Reads PDFs.',
  files: [{ path: 'SKILL.md', size: 120 }],
  skipped: [],
  has_scripts: false,
  audits: [],
  blocked_by: null,
  conflict: 'none',
};

const INSTALLED: LibraryInstalledItem = {
  skill_id: 's1',
  name: 'pdf',
  portal: 'skills_sh',
  repository: 'acme/skills',
  path: 'skills/pdf',
  ref: 'HEAD',
  commit_sha: 'a'.repeat(40),
  update: 'available',
};

function reading(state: LibraryDialogState = initialLibraryState('search')): LibraryDialogState {
  return libraryDialogReducer(state, { type: 'busy', busy: 'reading' });
}

describe('reading a skill', () => {
  it('shows its preview, and the way back returns to the tabs', () => {
    const shown = libraryDialogReducer(reading(), {
      type: 'read',
      answer: { preview: PREVIEW, choice: null },
      skillId: 'pdf',
    });
    expect(shown.view).toEqual({ kind: 'preview', preview: PREVIEW, skillId: 'pdf' });
    expect(shown.busy).toBeNull();
    expect(libraryDialogReducer(shown, { type: 'back' }).view).toEqual({ kind: 'browse' });
  });

  it('shows the folders to choose from when the repository holds several', () => {
    const choice = {
      repository: 'acme/skills',
      ref: 'HEAD',
      commit_sha: 'c'.repeat(40),
      folders: ['a', 'b'],
    };
    const shown = libraryDialogReducer(reading(), {
      type: 'read',
      answer: { preview: null, choice },
      skillId: null,
    });
    expect(shown.view).toEqual({ kind: 'choosing', choice });
  });
});

describe('a refusal', () => {
  it('ends the request and stays until the next act', () => {
    const refusal = { key: 'settings.skills.library.errors.skill_library_not_found' };
    const refusedState = libraryDialogReducer(reading(), { type: 'refused', refusal });
    expect(refusedState).toMatchObject({ busy: null, refusal });
    expect(
      libraryDialogReducer(refusedState, { type: 'busy', busy: 'reading' }).refusal
    ).toBeNull();
    expect(libraryDialogReducer(refusedState, { type: 'tab', tab: 'address' }).refusal).toBeNull();
  });
});

describe('an update', () => {
  it('is read, then done on the installed tab', () => {
    const update: LibraryUpdatePreview = {
      preview: PREVIEW,
      changes: { added: [], removed: [], modified: ['SKILL.md'] },
    };
    const shown = libraryDialogReducer(reading(initialLibraryState('installed')), {
      type: 'update_read',
      skill: INSTALLED,
      update,
    });
    expect(shown.view).toEqual({ kind: 'update', skill: INSTALLED, update });
    expect(libraryDialogReducer(shown, { type: 'done', tab: 'installed' })).toEqual(
      initialLibraryState('installed')
    );
  });
});

describe('a tab value', () => {
  it('is one of the three, or refused', () => {
    expect(isLibraryTab('installed')).toBe(true);
    expect(isLibraryTab('elsewhere')).toBe(false);
  });
});
