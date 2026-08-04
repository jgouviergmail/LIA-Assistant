/**
 * One icon per briefing card — the single mapping (owner rule 2026-08-05:
 * a title never goes without an icon).
 *
 * Exhaustive BY TYPE: `Record<BriefingSection, …>` makes the compiler refuse
 * a new card without its icon (the boot-time-completeness doctrine, enforced
 * at build time instead). The icons mirror what each card component renders
 * in its own header — this table is what the settings list (and any future
 * card chrome) reads, so the two can never drift.
 */

import type { LucideIcon } from 'lucide-react';
import {
  Bell,
  Cake,
  Calendar,
  CloudSun,
  FileText,
  Heart,
  ListTodo,
  Mail,
  Sparkles,
} from 'lucide-react';

import type { BriefingSection } from '@/types/briefing';

export const BRIEFING_CARD_ICONS: Record<BriefingSection, LucideIcon> = {
  weather: CloudSun,
  agenda: Calendar,
  mails: Mail,
  birthdays: Cake,
  reminders: Bell,
  health: Heart,
  for_you: Sparkles,
  tasks: ListTodo,
  documents: FileText,
};
