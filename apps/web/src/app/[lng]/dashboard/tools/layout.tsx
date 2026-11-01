'use client';

import type { ReactNode } from 'react';

import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** The « Tools » section (ADR-369): the rail, read once, around every tool page. */
export default function ToolsLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}) {
  const lng = useLanguageParam(params);
  return <WorkbenchShell lng={lng}>{children}</WorkbenchShell>;
}
