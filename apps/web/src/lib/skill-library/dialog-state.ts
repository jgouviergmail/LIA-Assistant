/**
 * The skill library dialog as a pure state machine (ADR-327).
 *
 * The dialog browses (three tabs), then shows ONE thing over them: the folders
 * of a repository to choose from, a skill read before its install, or the
 * next version of an installed skill. The tabs stay mounted underneath — the
 * search text, its results and a pasted address survive a look at a skill and
 * the way back. One request runs at a time (`busy`), and a refusal is kept
 * until the next act, as the sentence the API named.
 */
import type { LibraryRefusal } from './errors';
import type {
  LibraryFolderChoice,
  LibraryInstalledItem,
  LibraryPreview,
  LibraryPreviewAnswer,
  LibraryUpdatePreview,
} from './types';

const TABS = ['search', 'address', 'installed'] as const;

export type LibraryTab = (typeof TABS)[number];

/** Whether a tab value (Radix hands a string) is one of the dialog's tabs. */
export function isLibraryTab(value: string): value is LibraryTab {
  return (TABS as readonly string[]).includes(value);
}

export type LibraryView =
  | { kind: 'browse' }
  | { kind: 'choosing'; choice: LibraryFolderChoice }
  | { kind: 'preview'; preview: LibraryPreview; skillId: string | null }
  | { kind: 'update'; skill: LibraryInstalledItem; update: LibraryUpdatePreview };

export type LibraryBusy = 'reading' | 'installing' | null;

export interface LibraryDialogState {
  tab: LibraryTab;
  view: LibraryView;
  busy: LibraryBusy;
  refusal: LibraryRefusal | null;
}

export type LibraryDialogAction =
  | { type: 'tab'; tab: LibraryTab }
  | { type: 'busy'; busy: Exclude<LibraryBusy, null> }
  | { type: 'read'; answer: LibraryPreviewAnswer; skillId: string | null }
  | { type: 'update_read'; skill: LibraryInstalledItem; update: LibraryUpdatePreview }
  | { type: 'done'; tab: LibraryTab }
  | { type: 'refused'; refusal: LibraryRefusal }
  | { type: 'back' };

export function initialLibraryState(tab: LibraryTab): LibraryDialogState {
  return { tab, view: { kind: 'browse' }, busy: null, refusal: null };
}

/** What a preview answer shows: the skill, or the folders to choose from first. */
function viewOf(answer: LibraryPreviewAnswer, skillId: string | null): LibraryView {
  if (answer.preview) return { kind: 'preview', preview: answer.preview, skillId };
  if (answer.choice) return { kind: 'choosing', choice: answer.choice };
  return { kind: 'browse' };
}

export function libraryDialogReducer(
  state: LibraryDialogState,
  action: LibraryDialogAction
): LibraryDialogState {
  switch (action.type) {
    case 'tab':
      return { ...state, tab: action.tab, view: { kind: 'browse' }, refusal: null };
    case 'busy':
      return { ...state, busy: action.busy, refusal: null };
    case 'read':
      return { ...state, busy: null, view: viewOf(action.answer, action.skillId) };
    case 'update_read':
      return {
        ...state,
        busy: null,
        view: { kind: 'update', skill: action.skill, update: action.update },
      };
    case 'done':
      return initialLibraryState(action.tab);
    case 'refused':
      return { ...state, busy: null, refusal: action.refusal };
    case 'back':
      return { ...state, view: { kind: 'browse' }, refusal: null };
  }
}
