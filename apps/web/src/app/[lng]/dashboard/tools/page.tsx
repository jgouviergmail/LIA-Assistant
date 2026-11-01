'use client';

import { WorkbenchLanding } from '@/components/workbench/WorkbenchLanding';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools`: the first ready tool on a desktop, the rail below `lg`. */
export default function ToolsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <WorkbenchLanding lng={lng} />;
}
