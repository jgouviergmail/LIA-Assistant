/**
 * What a `local` slash command does to the application.
 *
 * The registry (`slash-commands.ts`) says a command EXISTS and how it is
 * presented; this says what pressing it performs. The two are separate on
 * purpose — the registry is also read by the settings form to refuse reserved
 * ids, and it has no business knowing routes.
 *
 * Extracted from the chat page, where it was an `if` chain with no test inside
 * a component that has none: a `local` command wired to nothing looked exactly
 * like one that worked, right up to the press. A sibling test asserts the two
 * tables agree in BOTH directions, so a command added to one and forgotten in
 * the other fails CI rather than shipping as a dead menu entry.
 */

/** Side effects a local command may request from the page. */
export interface LocalCommandHandlers {
  /** Navigate to an app path (the caller localizes it). */
  navigate: (path: string) => void;
  /** Reveal and focus the conversation-history search. */
  openSearch: () => void;
}

const HANDLERS: Record<string, (h: LocalCommandHandlers) => void> = {
  briefing: h => h.navigate('/dashboard'),
  spaces: h => h.navigate('/dashboard/spaces'),
  search: h => h.openSearch(),
};

/** Ids this module knows how to run — the oracle of the agreement test. */
export const LOCAL_COMMAND_IDS: readonly string[] = Object.keys(HANDLERS);

/**
 * Run a local command, if it is one.
 *
 * Args:
 *   commandId: Id picked in the slash menu.
 *   handlers: The page's side effects.
 */
export function runLocalCommand(commandId: string, handlers: LocalCommandHandlers): void {
  HANDLERS[commandId]?.(handlers);
}
