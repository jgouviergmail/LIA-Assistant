'use client';

import { TasksTool } from '@/components/workbench/tasks/TasksTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/tasks`: the account's task lists and tasks, by hand (ADR-369). */
export default function TasksPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <TasksTool lng={lng} />;
}
