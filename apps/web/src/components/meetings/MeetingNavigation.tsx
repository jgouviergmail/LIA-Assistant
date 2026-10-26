'use client';
import { createContext, useContext, type ReactNode } from 'react';
import Link from 'next/link';

const Navigation = createContext<((id: string) => void) | undefined>(undefined);
export function MeetingNavigationProvider({
  onOpen,
  children,
}: {
  onOpen?: (id: string) => void;
  children: ReactNode;
}) {
  return <Navigation value={onOpen}>{children}</Navigation>;
}
/** Async imports and links share the host's local navigation contract. */
export function useMeetingNavigation() {
  return useContext(Navigation);
}
/** A native route remains a link; an embedded reader keeps its own local navigation. */
export function MeetingOpenLink({
  id,
  href,
  children,
  className,
}: {
  id: string;
  href: string;
  children: ReactNode;
  className?: string;
}) {
  const open = useMeetingNavigation();
  return open ? (
    <button type="button" className={className + ' text-left'} onClick={() => open(id)}>
      {children}
    </button>
  ) : (
    <Link prefetch={false} href={href} className={className}>
      {children}
    </Link>
  );
}
