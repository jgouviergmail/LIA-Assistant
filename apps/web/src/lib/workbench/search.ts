/**
 * One search across the tools (ADR-369, lot 13): where a hit opens, and whether anything can be
 * searched at all.
 *
 * Pure: the dialog reads it. A hit opens on the address its tool already reads, so a link to it
 * works like any other link of that tool.
 */
import type { Language } from '@/i18n/settings';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { MAIL_INBOX } from './mail';
import { toolPath } from './tools';
import type { SearchableTool, SearchHit, WorkbenchAvailability, WorkbenchToolId } from './types';

/** Each tool's address of a hit: what a person opening it from that tool would reach. */
const ADDRESSES: Readonly<Record<SearchableTool, (hit: SearchHit) => Record<string, string>>> = {
  mail: hit => ({ folder: hit.mail_folder ?? MAIL_INBOX, id: hit.id }),
  calendar: hit => ({ day: hit.day ?? '', cal: hit.calendar_id ?? '', event: hit.id }),
  contacts: hit => ({ contact: hit.id }),
  files: (hit): Record<string, string> => (hit.is_folder ? { folder: hit.id } : { file: hit.id }),
};

function searches(tool: WorkbenchToolId): tool is SearchableTool {
  return tool in ADDRESSES;
}

/** @returns Whether at least one ready tool can be searched. */
export function searchOffered(availability: WorkbenchAvailability): boolean {
  return availability.tools.some(item => searches(item.tool) && item.state === 'ready');
}

/** @returns The tool's own page. */
export function toolHref(tool: WorkbenchToolId, lng: Language): string {
  return buildLocalizedPath(toolPath(tool), lng);
}

/** @returns Where a hit opens in its tool. */
export function hitHref(tool: SearchableTool, hit: SearchHit, lng: Language): string {
  return `${toolHref(tool, lng)}?${new URLSearchParams(ADDRESSES[tool](hit))}`;
}
