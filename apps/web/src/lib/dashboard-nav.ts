/**
 * The dashboard's destinations, in one place (A2, extended by R01).
 *
 * Below `lg` (raised from `md` by R01 — five destinations clip in fr/de/es/it
 * between 768 and 1024 px) the header's `<nav>` is hidden, and nothing once
 * replaced it: a phone user could reach the dashboard (through the logo) and
 * no other page at all. The way back existed only by typing a URL.
 *
 * This table is what both surfaces render: the desktop `<nav>` and the mobile
 * menu the logo opens. Two lists would drift, and the one that drifted would be
 * the mobile one — the one nobody looks at on a large screen.
 *
 * Knowledge spaces also have their own destination after the workboard; the
 * chat indicator and settings section remain direct doors to the same screen.
 */

/**
 * The flags a destination may depend on, named after the deployment flags of
 * `useAppConfig().features`. What each is WORTH is decided by
 * `offeredDestinations` (`components/dashboard/offered-destinations.ts`): what
 * the instance offers now, the operator's switch included — never the
 * deployment ceiling alone.
 */
export interface DestinationFeatures {
  world_enabled?: boolean;
  meetings_enabled?: boolean;
  workbench_enabled?: boolean;
  sms_enabled?: boolean;
  rag_spaces_enabled?: boolean;
  workboard_enabled?: boolean;
}

/** A destination of the dashboard shell. */
export interface DashboardDestination {
  /** Path suffix appended to the localized `/dashboard` root ('' = the root). */
  segment:
    | ''
    | 'chat'
    | 'tools'
    | 'world'
    | 'relations'
    | 'sms'
    | 'meetings'
    | 'workboard'
    | 'spaces'
    | 'notifications'
    | 'settings'
    | 'faq';
  /** i18n key of the visible label. */
  labelKey: string;
  /**
   * Instance flag the destination needs. Absent = always offered. A gated
   * destination whose flag is off is not a dead link, it does not exist:
   * every renderer reads the table through `offeredDestinations`.
   */
  feature?: keyof DestinationFeatures;
  /**
   * Stamp the link with the screen the reader is leaving (`?from=`), so the
   * destination can offer a way BACK to it (`lib/back-origin.ts`).
   *
   * Declared per destination rather than applied to all: an origin nobody
   * reads is a query parameter on every URL of the app, and only a screen
   * that draws a back button has any use for one. Meetings is that screen —
   * six doors lead to it and its list had no way back at all (owner,
   * 2026-09-10).
   */
  carriesOrigin?: boolean;
}

/**
 * Display order, shared by the desktop nav and the mobile menu.
 *
 * 2026-08-03: `notifications` joins the table, to the right of `relations` —
 * what LIA sends the reader was scattered across four settings sections
 * (device notifications, proactivity, interests, channels) with no single
 * place answering "what reached me, and what is coming?".
 *
 * 2026-09-03 (ADR-258): `meetings` joins between `relations` and
 * `notifications` — the recordings and their minutes had a page, a settings
 * section and a slash command, but no door in the header. SEVEN labels is the
 * widest this row has ever been; the renderer keeps labels from `xl`, and the
 * header paid for the seventh elsewhere: the language control shows its flag
 * alone at every width (the popup names the languages) and the personality
 * title waits for `2xl`. The label is deliberately SHORT in every locale.
 *
 * 2026-10-31 (ADR-369): `tools` joins the row — the « Tools » section where
 * the person reads and acts on their own services by hand. It is gated like
 * the world: offered only where the instance offers it NOW
 * (`workbenchAvailable`, the operator's switch included). NINE labels fit the
 * `2xl` row in German only with the short « Start » and « Tools » (measured on
 * dev: « Startseite » + « Werkzeuge » overflowed by 49 px, every other locale
 * fitting). The row is capped at 1536 px, so a wider breakpoint buys NO room:
 * a tenth destination must be paid for elsewhere.
 *
 * 2026-10-31 (owner): `tools` sits right after `world`, whose label is « 3D »
 * in every language.
 *
 * 2026-10-31 (owner): `sms` joins right after `relations` — the SMS themselves
 * (consult, block a sender, erase), moved out of Settings › SMS, which keeps
 * how SMS reach LIA. Gated like the tools: offered where the instance offers SMS
 * NOW (`smsAvailable`, the operator's switch included).
 *
 * 2026-10-31 (owner): the desktop row draws the destinations as ICONS ALONE at
 * every width — the label is the accessible name and the tooltip, and the menu
 * the logo opens below `lg` still writes it out. Ten labels no longer fit the
 * `2xl` row (measured: the last destination ran under the controls in
 * fr/de/es/it at 1536 px), and the row's width stopped depending on how long a
 * label is in one language.
 *
 * 2026-11-04 (owner): the row stands on the pages' rail, so a wider window gives
 * it room up to the rail's ceiling, where it was capped at 1536 px.
 *
 * 2026-11-11 (owner): `workboard` joins right after `meetings`. ADR-276 had
 * refused the board a door here (D16: seven labels was the measured maximum)
 * and reached it from a settings section; the row has drawn icons alone since
 * 2026-10-31, so a twelfth slot is 40 px, and the settings section is gone —
 * its figures stand above the board's own filters. Gated like the tools and
 * the SMS: offered where the instance offers the board NOW
 * (`workboardAvailable`, the operator's switch included).
 */
export const DASHBOARD_DESTINATIONS: readonly DashboardDestination[] = [
  { segment: '', labelKey: 'navigation.dashboard' },
  { segment: 'chat', labelKey: 'navigation.chat' },
  { segment: 'world', labelKey: 'navigation.world', feature: 'world_enabled' },
  { segment: 'tools', labelKey: 'navigation.tools', feature: 'workbench_enabled' },
  { segment: 'relations', labelKey: 'navigation.relations' },
  { segment: 'sms', labelKey: 'navigation.sms', feature: 'sms_enabled' },
  {
    segment: 'meetings',
    labelKey: 'navigation.meetings',
    feature: 'meetings_enabled',
    carriesOrigin: true,
  },
  { segment: 'workboard', labelKey: 'navigation.workboard', feature: 'workboard_enabled' },
  { segment: 'spaces', labelKey: 'navigation.spaces', feature: 'rag_spaces_enabled' },
  { segment: 'notifications', labelKey: 'navigation.notifications' },
  { segment: 'settings', labelKey: 'navigation.settings' },
  { segment: 'faq', labelKey: 'navigation.faq' },
];

/**
 * The header row's icon geometry from `lg` (owner, 2026-10-31): every icon —
 * a destination or a control — takes this 36 px slot, and both groups space
 * their icons by this gap, so the row stands at ONE pitch on both sides. Below
 * `lg` the destinations live in the logo's menu and the controls keep their
 * 44 px touch target (both pinned by the header-reachability spec). Whole
 * literal classes: Tailwind only generates what it reads written out.
 */
export const HEADER_ICON_SLOT = 'lg:h-9 lg:w-9 lg:min-w-9 lg:px-0';
export const HEADER_ICON_GAP = 'lg:gap-1';

/**
 * The horizontal frame of a dashboard page, which the notice above it takes too.
 * The rail is every page's and the header's, centred under the theme's
 * `--container-page` (owner, 2026-11-04: half as wide again as the 1280 px it was,
 * so that the interface breathes when the screen allows it). The window is the
 * « Tools » section's (owner, 2026-11-04: on any screen a tool had the rail's
 * 1216 px): from `lg` the whole window behind a 16 px gutter, and below `lg` the
 * same frame as the rail. Whole literal classes, as above.
 */
export const PAGE_FRAME_RAIL = 'w-full max-w-page mx-auto px-4 sm:px-6 lg:px-8';
export const PAGE_FRAME_WINDOW = 'w-full px-4 sm:px-6 lg:px-4';

/**
 * The table, filtered by what each flag is worth.
 *
 * The rule alone: it does not decide a flag's value. Production code reaches
 * it through `offeredDestinations`, its one caller (guarded), which gives each
 * flag the effective state of its capability.
 *
 * Args:
 *   features: The value of each flag, possibly unknown — an unknown flag
 *     reads as OFF, so a gated destination never flashes in before the
 *     configuration answers.
 *
 * Returns:
 *   The table, in order, without the gated destinations whose flag is off.
 */
export function visibleDestinations(
  features: DestinationFeatures | null | undefined
): readonly DashboardDestination[] {
  return DASHBOARD_DESTINATIONS.filter(
    destination => destination.feature === undefined || features?.[destination.feature] === true
  );
}

/**
 * Route of a destination, before localization.
 *
 * Args:
 *   segment: The destination's segment.
 *
 * Returns:
 *   `/dashboard` for the root, `/dashboard/<segment>` otherwise.
 */
export function destinationPath(segment: DashboardDestination['segment']): string {
  return segment ? `/dashboard/${segment}` : '/dashboard';
}

// Deliberately NO active-state helper here: the layout already owns
// `isActiveRoute`, which handles nested routes (`/dashboard/settings/x` still
// highlights Settings). A second implementation would be the one that drifts.
