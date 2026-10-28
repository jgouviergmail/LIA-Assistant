'use client';

import { createContext, useCallback, useContext, type ComponentProps, type ReactNode } from 'react';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { isLanguage } from '@/i18n/settings';
import { isSettingsSectionToken, type SettingsSectionToken } from '@/lib/settings-sections';
import { filtersFromParams } from '@/lib/workboard/filters-url';
import type { BoardFilters } from '@/types/workboard';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { z } from '@/lib/zod';

export type DashboardDestination =
  | { kind: 'settings'; token: SettingsSectionToken | null }
  | { kind: 'draft'; draft: string }
  | { kind: 'workboard'; filters: BoardFilters; ticketId?: string }
  | { kind: 'meeting'; id: string }
  | { kind: 'gallery'; tab: GeneratedAssetTab }
  | { kind: 'registers' }
  | { kind: 'sms'; messageId: string };
export type DashboardNavigate = (destination: DashboardDestination) => boolean;
const Navigation = createContext<DashboardNavigate | undefined>(undefined);
export function DashboardNavigationProvider({
  onNavigate,
  children,
}: {
  onNavigate?: DashboardNavigate;
  children: ReactNode;
}) {
  return <Navigation value={onNavigate}>{children}</Navigation>;
}
export const useDashboardNavigation = () => useContext(Navigation);

/** Interpret only the native paths the dashboard itself produces, never arbitrary URLs. */
export function dashboardDestination(href: string): DashboardDestination | null {
  const path = dashboardPath(href);
  if (!path) return null;
  const { url, parts } = path;
  switch (parts[0]) {
    case 'settings':
      return parts.length === 1 ? settingsDestination(url.searchParams) : null;
    case 'chat':
      return parts.length === 1 ? draftDestination(url.searchParams) : null;
    case 'workboard':
      return workboardDestination(parts, url.searchParams);
    case 'meetings': {
      const id = parts.length === 2 ? decodeId(parts[1]) : null;
      return id ? { kind: 'meeting', id } : null;
    }
    case 'actions':
      return parts.length === 1 ? { kind: 'registers' } : null;
    default:
      return null;
  }
}
function dashboardPath(href: string): { url: URL; parts: string[] } | null {
  if (!href.startsWith('/') || href.startsWith('//') || href.includes('\\')) return null;
  const url = new URL(href, 'https://lia-dashboard.invalid');
  const parts = url.pathname.split('/').filter(Boolean);
  if (isLanguage(parts[0])) parts.shift();
  if (parts.shift() !== 'dashboard') return null;
  return { url, parts };
}
function decodeId(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const id = decodeURIComponent(value);
    return z.uuid().safeParse(id).success ? id : null;
  } catch {
    return null;
  }
}
function settingsDestination(params: URLSearchParams): DashboardDestination | null {
  const token = params.get('section');
  if (token === null) return { kind: 'settings', token: null };
  if (!isSettingsSectionToken(token)) return null;
  if (token === 'sms' && params.has('message')) {
    const messageId = decodeId(params.get('message') ?? undefined);
    return messageId ? { kind: 'sms', messageId } : null;
  }
  return { kind: 'settings', token };
}
function draftDestination(params: URLSearchParams): DashboardDestination | null {
  if (params.has('intent') || params.has('voice')) return null;
  return { kind: 'draft', draft: params.get('draft') ?? '' };
}
function workboardDestination(
  parts: string[],
  params: URLSearchParams
): DashboardDestination | null {
  if (parts.length > 2) return null;
  const named = parts[1] ?? params.get('ticket');
  const ticketId = named ? decodeId(named) : null;
  if (named && !ticketId) return null;
  return {
    kind: 'workboard',
    filters: filtersFromParams(params),
    ...(ticketId ? { ticketId } : {}),
  };
}

/** Preserve anchors, keyboard/modifier semantics and the ordinary route outside an embedded host. */
export function DashboardLink({
  href,
  children,
  onClick,
  ...props
}: Omit<ComponentProps<typeof Link>, 'href'> & { href: string }) {
  const navigation = useDashboardNavigation();
  const { t } = useTranslation();
  const destination = dashboardDestination(href);
  const departure = navigation && !destination;
  return (
    <Link
      {...props}
      href={href}
      prefetch={navigation ? false : props.prefetch}
      onClick={event => {
        onClick?.(event);
        if (!navigation || !destination || !plainNavigation(event, props)) return;
        event.preventDefault();
        navigation(destination);
      }}
    >
      {children}
      {departure && (
        <>
          <ExternalLink className="ml-1 inline size-3 shrink-0" aria-hidden="true" />
          <span className="sr-only">{t('world.dashboard.leaves_world')}</span>
        </>
      )}
    </Link>
  );
}
function plainNavigation(
  event: React.MouseEvent<HTMLAnchorElement>,
  props: { target?: string; download?: unknown }
): boolean {
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    ![event.ctrlKey, event.metaKey, event.shiftKey, event.altKey].some(Boolean) &&
    (!props.target || props.target === '_self') &&
    !props.download
  );
}
export function useDashboardRoute(fallback: (href: string) => void) {
  const navigation = useDashboardNavigation();
  return useCallback(
    (href: string) => {
      const destination = dashboardDestination(href);
      if (navigation && destination) {
        navigation(destination);
        return;
      }
      fallback(href);
    },
    [navigation, fallback]
  );
}
/** Executable intents retain the native deep-link and replay guard byte for byte. */
export function useDashboardChat() {
  return useDashboardRoute(openChatDeepLink);
}
