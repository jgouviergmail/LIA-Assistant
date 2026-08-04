/**
 * Single source of truth for the "/more" small-attentions page: 32 cards in
 * 6 moment sections, each card carrying one lucide icon and the list of
 * translated micro-labels its animated scene needs.
 *
 * ANTI-REGRESSION CONTRACT: the guard test
 * `__tests__/more-content-coverage.test.ts` asserts the structure (32 unique
 * cards, icon/scene-label completeness), the level contract (keys disjoint
 * from the editorial landing's REQUIRED_FEATURE_KEYS — this page presents
 * craft, one level below capabilities), and the i18n content (every
 * `more.*` key present and non-empty in all 6 locales, no digits in card
 * copy). Adding, renaming, or dropping a card is therefore always a
 * deliberate edit of this file plus its locales — never a silent side
 * effect.
 */

import type { LucideIcon } from 'lucide-react';
import {
  Orbit,
  BellRing,
  Search,
  ChevronsDownUp,
  Vibrate,
  Accessibility,
  AlertTriangle,
  AppWindow,
  ArrowDownCircle,
  ClipboardPaste,
  Clock,
  Coins,
  Drama,
  FileUp,
  Gauge,
  Handshake,
  History,
  LayoutGrid,
  Link2,
  ListChecks,
  Menu,
  PanelsTopLeft,
  MessageSquarePlus,
  PanelTop,
  MonitorSmartphone,
  Smartphone,
  Paperclip,
  PencilLine,
  PenLine,
  Radio,
  RefreshCw,
  RotateCcw,
  Share2,
  SlashSquare,
  Sparkles,
  Star,
  TextSelect,
  TextSearch,
  ThumbsUp,
  Zap,
} from 'lucide-react';

export interface MoreSectionConfig {
  /** Stable section identifier (scene-file suffix + anchors). */
  id: 'write' | 'respond' | 'recover' | 'find' | 'daily' | 'unseen';
  /** i18n suffix under `more.sections.`. */
  key: 's1' | 's2' | 's3' | 's4' | 's5' | 's6';
  /** Display number of the section heading eyebrow. */
  num: string;
  /** Alternating card background for visual rhythm (editorial pattern). */
  tinted: boolean;
  /** Card keys in display order. */
  cards: readonly string[];
}

export const MORE_SECTIONS: readonly MoreSectionConfig[] = [
  {
    id: 'write',
    key: 's1',
    num: '01',
    tinted: false,
    cards: ['draft_survives', 'slash_commands', 'paste_screenshot', 'drop_zone'],
  },
  {
    id: 'respond',
    key: 's2',
    num: '02',
    tinted: true,
    cards: [
      'followup_chips',
      'scroll_return',
      'bubble_actions',
      'provenance_why',
      'selection_actions',
      'peer_actions',
      'share_export',
      'backstage',
    ],
  },
  {
    id: 'recover',
    key: 's3',
    num: '03',
    tinted: false,
    cards: [
      'actionable_errors',
      'retry_turn',
      'honest_freshness',
      'quota_warning',
      'image_expiry',
      'attachment_limits',
      'fix_commitment',
    ],
  },
  {
    id: 'find',
    key: 's4',
    num: '04',
    tinted: true,
    cards: [
      'settings_search',
      'deep_links',
      'history_search',
      'mobile_logo_nav',
      'relation_star',
      'relation_sections',
    ],
  },
  {
    id: 'daily',
    key: 's5',
    num: '05',
    tinted: false,
    cards: [
      'briefing_custom',
      'card_actions',
      'alerts_hub',
      'folded_settings',
      'starter_checklist',
      'empty_starters',
      'pwa',
    ],
  },
  {
    id: 'unseen',
    key: 's6',
    num: '06',
    tinted: true,
    cards: [
      'background_response',
      'capability_map',
      'widgets_travel',
      'cost_transparency',
      'haptics',
      'a11y_care',
      'frosted_glass',
      'narrow_screens',
    ],
  },
] as const;

/** Flat card-key inventory, derived — display order. */
export const MORE_CARD_KEYS: readonly string[] = MORE_SECTIONS.flatMap(s => [...s.cards]);

/** One lucide icon per card (guard-enforced completeness). */
export const CARD_ICONS: Record<string, LucideIcon> = {
  draft_survives: PenLine,
  slash_commands: SlashSquare,
  paste_screenshot: ClipboardPaste,
  drop_zone: FileUp,
  followup_chips: MessageSquarePlus,
  scroll_return: ArrowDownCircle,
  bubble_actions: ThumbsUp,
  selection_actions: TextSelect,
  peer_actions: Handshake,
  share_export: Share2,
  backstage: Drama,
  actionable_errors: AlertTriangle,
  retry_turn: RotateCcw,
  honest_freshness: RefreshCw,
  quota_warning: Gauge,
  image_expiry: Clock,
  attachment_limits: Paperclip,
  fix_commitment: PencilLine,
  settings_search: TextSearch,
  deep_links: Link2,
  history_search: History,
  mobile_logo_nav: Menu,
  relation_star: Star,
  relation_sections: PanelsTopLeft,
  briefing_custom: LayoutGrid,
  card_actions: Zap,
  starter_checklist: ListChecks,
  empty_starters: Sparkles,
  pwa: MonitorSmartphone,
  background_response: Radio,
  widgets_travel: AppWindow,
  cost_transparency: Coins,
  a11y_care: Accessibility,
  haptics: Vibrate,
  folded_settings: ChevronsDownUp,
  frosted_glass: PanelTop,
  provenance_why: Search,
  alerts_hub: BellRing,
  capability_map: Orbit,
  narrow_screens: Smartphone,
};

/**
 * Translated micro-labels each animated scene needs, as i18n suffixes under
 * `more.scenes.<cardKey>.`. Everything else inside a stage is skeleton bars
 * and icons — scenes stay language-light by design.
 */
export const SCENE_LABEL_KEYS: Readonly<Record<string, readonly string[]>> = {
  draft_survives: ['typing'],
  slash_commands: [],
  paste_screenshot: [],
  drop_zone: [],
  followup_chips: ['chip1', 'chip2'],
  scroll_return: [],
  bubble_actions: ['copied'],
  selection_actions: ['action'],
  peer_actions: ['reply'],
  share_export: [],
  backstage: [],
  actionable_errors: ['cause', 'action'],
  retry_turn: [],
  honest_freshness: ['fresh', 'retry'],
  quota_warning: ['warned'],
  image_expiry: [],
  attachment_limits: ['limit'],
  fix_commitment: ['before', 'after'],
  settings_search: ['query', 'row1', 'row2'],
  deep_links: [],
  history_search: ['query'],
  mobile_logo_nav: [],
  relation_star: [],
  relation_sections: ['section'],
  briefing_custom: [],
  card_actions: ['chip1', 'chip2'],
  starter_checklist: [],
  empty_starters: ['s1', 's2', 's3'],
  pwa: [],
  background_response: ['ready'],
  widgets_travel: [],
  cost_transparency: [],
  haptics: [],
  folded_settings: [],
  a11y_care: [],
  frosted_glass: [],
  provenance_why: [],
  alerts_hub: [],
  capability_map: [],
  narrow_screens: [],
};
