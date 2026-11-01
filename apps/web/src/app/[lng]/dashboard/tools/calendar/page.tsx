'use client';

import { CalendarTool } from '@/components/workbench/calendar/CalendarTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/calendar`: the account's calendars and events, by hand (ADR-369). */
export default function CalendarPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <CalendarTool lng={lng} />;
}
