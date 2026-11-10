/** Shared destination illustrations for the desktop rail and the phone's LIA menu. */
import {
  Bell,
  ClipboardList,
  HelpCircle,
  LayoutDashboard,
  Library,
  Map,
  MessageSquare,
  MessageSquareText,
  Settings,
  Users,
  Wrench,
  type LucideIcon,
} from '@/lib/icons';

import type { DashboardDestination } from './dashboard-nav';

/** A new destination cannot ship without its illustration on both surfaces. */
export const DESTINATION_ICONS: Readonly<Record<DashboardDestination['segment'], LucideIcon>> = {
  '': LayoutDashboard,
  chat: MessageSquare,
  tools: Wrench,
  world: Map,
  relations: Users,
  sms: MessageSquareText,
  meetings: ClipboardList,
  spaces: Library,
  notifications: Bell,
  settings: Settings,
  faq: HelpCircle,
};
