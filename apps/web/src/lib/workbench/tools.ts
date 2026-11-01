/**
 * The rail's model (ADR-369): the six tools in their order, the two groups the
 * rail draws, the tool the section opens on, and the tool a URL names.
 *
 * Pure: the rail, the shell and the landing page read it.
 */
import {
  BookUser,
  CalendarDays,
  FolderOpen,
  Lightbulb,
  ListChecks,
  Mail,
  type LucideIcon,
} from 'lucide-react';

import type { WorkbenchAvailability, WorkbenchToolAvailability, WorkbenchToolId } from './types';

/** One tool as the rail draws it. */
export interface WorkbenchToolSpec {
  id: WorkbenchToolId;
  icon: LucideIcon;
  /** i18n key of its name. */
  labelKey: string;
}

/** Every tool's icon — completeness enforced by the type: a new tool needs one. */
const ICONS: Readonly<Record<WorkbenchToolId, LucideIcon>> = {
  mail: Mail,
  calendar: CalendarDays,
  tasks: ListChecks,
  contacts: BookUser,
  files: FolderOpen,
  lights: Lightbulb,
};

/** Rail order (spec §13). */
const ORDER: readonly WorkbenchToolId[] = [
  'mail',
  'calendar',
  'tasks',
  'contacts',
  'files',
  'lights',
];

/**
 * @param id - A tool.
 * @returns Its spec.
 */
export function toolSpec(id: WorkbenchToolId): WorkbenchToolSpec {
  return { id, icon: ICONS[id], labelKey: `workbench.tools.${id}.label` };
}

/** The six tools, in rail order. */
export const WORKBENCH_TOOLS: readonly WorkbenchToolSpec[] = ORDER.map(toolSpec);

/** The section's root, before localization. */
export const WORKBENCH_ROOT = '/dashboard/tools';

/** The `lg` breakpoint: from here a list and its detail stand side by side. */
export const WORKBENCH_DESKTOP = '(min-width: 1024px)';

/**
 * A tool's pane height from `lg`: the viewport less the header, the rail row
 * above the tool (3.25rem), the tool's heading and the banners — so a list and
 * its detail scroll inside the pane, never the page. ONE value for every tool.
 */
export const WORKBENCH_PANE_HEIGHT =
  'lg:h-[calc(100dvh-16.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px)-var(--radio-banner-h,0px))]';

const TOOL_IDS: ReadonlySet<string> = new Set(ORDER);

function isToolId(value: string): value is WorkbenchToolId {
  return TOOL_IDS.has(value);
}

/**
 * @param id - A tool.
 * @returns Its route, before localization.
 */
export function toolPath(id: WorkbenchToolId): string {
  return `${WORKBENCH_ROOT}/${id}`;
}

/** The rail's two groups (D6): usable or broken tools, and the ones to connect. */
export interface RailGroups {
  /** Ready tools and tools to reconnect (with a warning), in rail order. */
  tools: WorkbenchToolAvailability[];
  /** Tools a provider can be connected for, in rail order. */
  toConnect: WorkbenchToolAvailability[];
}

/**
 * @param availability - What `GET /workbench` answered.
 * @returns The two groups; a tool the instance offers no provider for is in neither.
 */
export function railGroups(availability: WorkbenchAvailability): RailGroups {
  const ordered = WORKBENCH_TOOLS.flatMap(spec =>
    availability.tools.filter(item => item.tool === spec.id)
  );
  return {
    tools: ordered.filter(item => item.state === 'ready' || item.state === 'reconnect_required'),
    toConnect: ordered.filter(item => item.state === 'not_connected'),
  };
}

/**
 * The tool a desktop opens on: the first READY one in rail order.
 *
 * @param availability - What `GET /workbench` answered, if it has.
 * @returns The tool, or null when none is ready (the rail then names the exit).
 */
export function landingTool(
  availability: WorkbenchAvailability | null | undefined
): WorkbenchToolId | null {
  if (!availability) return null;
  return railGroups(availability).tools.find(item => item.state === 'ready')?.tool ?? null;
}

/**
 * The tool a localized pathname shows (`/fr/dashboard/tools/calendar`).
 *
 * @param pathname - The current pathname.
 * @returns The tool, or null for the section's root or anything else.
 */
export function toolOfPathname(pathname: string | null | undefined): WorkbenchToolId | null {
  const match = /\/dashboard\/tools\/([a-z]+)(?:\/|$)/.exec(pathname ?? '');
  const candidate = match?.[1];
  return candidate !== undefined && isToolId(candidate) ? candidate : null;
}
