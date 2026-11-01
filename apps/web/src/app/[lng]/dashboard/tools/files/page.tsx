'use client';

import { FilesTool } from '@/components/workbench/files/FilesTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/files`: the account's Drive, by hand (ADR-369). */
export default function FilesPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <FilesTool lng={lng} />;
}
