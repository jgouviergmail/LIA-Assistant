/**
 * The « Tools » panes a person sizes by hand on a large screen (owner request
 * 2026-10-31) — one declaration per pane, read by the pane's hook and its tests.
 *
 * `edge` is the edge of the pane its separator sits on (`end` its right edge,
 * `start` its left one), `initial` its width before anyone drags it (the
 * layout's own default, used until the pane is measured), `min`/`max` its
 * bounds in pixels and `share` the part of its row it may take, so the panes
 * beside it always keep room on a narrow window. A pane nobody resized keeps
 * the layout's own responsive widths.
 */
import type { PaneBounds } from '@/lib/pane-width';

export type WorkbenchPane =
  | 'mail.folders'
  | 'mail.list'
  | 'calendar.calendars'
  | 'calendar.detail'
  | 'tasks.lists'
  | 'tasks.editor'
  | 'contacts.list'
  | 'files.list';

export interface PaneSpec {
  edge: 'start' | 'end';
  initial: number;
  min: number;
  max: number;
  share: number;
  /** The separator's accessible name. */
  labelKey: string;
}

export const WORKBENCH_PANES: Record<WorkbenchPane, PaneSpec> = {
  'mail.folders': {
    edge: 'end',
    initial: 224,
    min: 160,
    max: 400,
    share: 0.25,
    labelKey: 'workbench.panes.mail_folders',
  },
  'mail.list': {
    edge: 'end',
    initial: 320,
    min: 260,
    max: 720,
    share: 0.45,
    labelKey: 'workbench.panes.mail_list',
  },
  'calendar.calendars': {
    edge: 'end',
    initial: 240,
    min: 180,
    max: 400,
    share: 0.25,
    labelKey: 'workbench.panes.calendar_calendars',
  },
  'calendar.detail': {
    edge: 'start',
    initial: 384,
    min: 280,
    max: 640,
    share: 0.45,
    labelKey: 'workbench.panes.calendar_detail',
  },
  'tasks.lists': {
    edge: 'end',
    initial: 224,
    min: 160,
    max: 400,
    share: 0.25,
    labelKey: 'workbench.panes.tasks_lists',
  },
  'tasks.editor': {
    edge: 'start',
    initial: 352,
    min: 280,
    max: 640,
    share: 0.45,
    labelKey: 'workbench.panes.tasks_editor',
  },
  'contacts.list': {
    edge: 'end',
    initial: 384,
    min: 260,
    max: 720,
    share: 0.6,
    labelKey: 'workbench.panes.contacts_list',
  },
  'files.list': {
    edge: 'end',
    initial: 416,
    min: 280,
    max: 800,
    share: 0.6,
    labelKey: 'workbench.panes.files_list',
  },
};

/** One arrow press on a separator, in pixels (four with Shift). */
export const WORKBENCH_PANE_STEP = 16;

/**
 * How wide a pane may be inside a row of a given width.
 *
 * @param spec - The pane's declaration.
 * @param rowWidth - The row holding it and its neighbours; 0 while unmeasured
 *   (the maximum is then the minimum's floor).
 */
export function paneBounds(spec: PaneSpec, rowWidth: number): PaneBounds {
  const room = Math.min(spec.max, Math.floor(rowWidth * spec.share));
  return { min: spec.min, max: Math.max(spec.min, room) };
}

/** Whether a value read back from the device is a pane this table declares. */
export function isWorkbenchPane(value: string): value is WorkbenchPane {
  return Object.hasOwn(WORKBENCH_PANES, value);
}
