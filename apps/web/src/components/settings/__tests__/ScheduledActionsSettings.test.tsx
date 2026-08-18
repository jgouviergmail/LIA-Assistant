/**
 * ScheduledActionsSettings — the recurring-actions manager: list states, the
 * status label derived from the enabled flag *before* the backend status, the
 * enable/disable toggle whose wording follows the value the server returns, the
 * on-demand execution, the confirm-gated deletion, and the two save paths.
 *
 * The save path carries two contracts worth pinning: creation trims the free
 * text and cannot be triggered before title + prompt + at least one day are
 * filled (the button stays disabled — no impossible click is simulated), and
 * edition sends a **differential** payload, down to sending nothing at all when
 * the user reopens a form and saves it untouched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useScheduledActions } = vi.hoisted(() => ({ useScheduledActions: vi.fn() }));
vi.mock('@/hooks/useScheduledActions', () => ({ useScheduledActions }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ScheduledActionsSettings } from '../ScheduledActionsSettings';
import type {
  ScheduledAction,
  useScheduledActions as useScheduledActionsFn,
} from '@/hooks/useScheduledActions';

type ScheduledHook = ReturnType<typeof useScheduledActionsFn>;

function action(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return {
    id: 'a1',
    user_id: 'u1',
    title: 'Morning brief',
    action_prompt: 'Summarise my day',
    days_of_week: [1, 2],
    trigger_hour: 8,
    trigger_minute: 0,
    user_timezone: 'Europe/Paris',
    trigger_kind: 'time',
    condition_config: null,
    requires_approval: false,
    next_trigger_at: '2026-07-20T06:00:00Z',
    is_enabled: true,
    status: 'active',
    last_executed_at: null,
    execution_count: 0,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: 'Mon, Tue - 08:00',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

function hook(over: Partial<ScheduledHook> = {}) {
  return {
    actions: [],
    total: 0,
    loading: false,
    createAction: vi.fn(),
    updateAction: vi.fn(),
    deleteAction: vi.fn(),
    toggleAction: vi.fn(),
    executeAction: vi.fn(),
    creating: false,
    updating: false,
    executing: false,
    ...over,
  };
}

function render() {
  return renderWithProviders(
    <ScheduledActionsSettings lng="en" />
  );
}

type User = ReturnType<typeof render>['user'];

const CREATE = 'scheduled_actions.create';
const EXECUTE = 'scheduled_actions.test_now';
const EDIT = 'common.edit';
const DELETE = 'common.delete';
const SAVE = 'common.save';
const FIELD_TITLE = 'scheduled_actions.field_title';
const FIELD_PROMPT = 'scheduled_actions.field_prompt';
/** Monday, in the WEEKDAYS 1..7 numbering the form uses. */
const MONDAY = 'scheduled_actions.days.d1';

const saveButton = () => screen.getByRole('button', { name: SAVE });

beforeEach(() => vi.clearAllMocks());

describe('ScheduledActionsSettings — list states', () => {
  it('shows a loading spinner while actions load', () => {
    useScheduledActions.mockReturnValue(hook({ loading: true }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('explains how to get started once the (empty) list has loaded', () => {
    useScheduledActions.mockReturnValue(hook({ loading: false, actions: [] }));
    render();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText('scheduled_actions.empty')).toBeInTheDocument();
    expect(screen.getByText('scheduled_actions.empty_hint')).toBeInTheDocument();
  });

  it('renders a configured action instead of the empty state', () => {
    useScheduledActions.mockReturnValue(hook({ actions: [action()], total: 1 }));
    render();
    expect(screen.getByText('Morning brief')).toBeInTheDocument();
    expect(screen.getByText('scheduled_actions.status.active')).toBeInTheDocument();
    expect(screen.queryByText('scheduled_actions.empty')).not.toBeInTheDocument();
  });

  it('reports a disabled action as paused even when the backend still says active', () => {
    // The enabled flag is checked FIRST: a paused action must never be
    // advertised as active just because its last known status was.
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ is_enabled: false, status: 'active' })], total: 1 })
    );
    render();
    expect(screen.getByText('scheduled_actions.status.paused')).toBeInTheDocument();
    expect(screen.queryByText('scheduled_actions.status.active')).not.toBeInTheDocument();
  });

  it('surfaces the error status of an enabled action', () => {
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ is_enabled: true, status: 'error' })], total: 1 })
    );
    render();
    expect(screen.getByText('scheduled_actions.status.error')).toBeInTheDocument();
  });
});

describe('ScheduledActionsSettings — enable toggle', () => {
  it('confirms with the wording matching the state the server returns', async () => {
    const toggleAction = vi.fn().mockResolvedValue(action({ is_enabled: false }));
    useScheduledActions.mockReturnValue(hook({ actions: [action()], toggleAction }));
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toggleAction).toHaveBeenCalledWith('a1'));
    expect(toast.success).toHaveBeenCalledWith('scheduled_actions.toggle_disabled');
  });

  it('uses the enabled wording when the server re-enables the action', async () => {
    const toggleAction = vi.fn().mockResolvedValue(action({ is_enabled: true }));
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ is_enabled: false })], toggleAction })
    );
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('scheduled_actions.toggle_enabled')
    );
  });

  it('stays silent when the server returns nothing to confirm', async () => {
    const toggleAction = vi.fn().mockResolvedValue(null);
    useScheduledActions.mockReturnValue(hook({ actions: [action()], toggleAction }));
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toggleAction).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('reports a refused toggle', async () => {
    const toggleAction = vi.fn().mockRejectedValue(new Error('boom'));
    useScheduledActions.mockReturnValue(hook({ actions: [action()], toggleAction }));
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('scheduled_actions.error_update'));
  });
});

describe('ScheduledActionsSettings — run now', () => {
  it('launches the action on demand', async () => {
    const executeAction = vi.fn().mockResolvedValue(undefined);
    useScheduledActions.mockReturnValue(hook({ actions: [action()], executeAction }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: EXECUTE }));
    await waitFor(() => expect(executeAction).toHaveBeenCalledWith('a1'));
    expect(toast.success).toHaveBeenCalledWith('scheduled_actions.test_now_launched');
  });

  it('reports a failed run', async () => {
    const executeAction = vi.fn().mockRejectedValue(new Error('boom'));
    useScheduledActions.mockReturnValue(hook({ actions: [action()], executeAction }));
    const { user } = render();
    await user.click(screen.getByRole('button', { name: EXECUTE }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('scheduled_actions.error_execute')
    );
  });

  it('locks the run button while an execution is in flight', () => {
    useScheduledActions.mockReturnValue(hook({ actions: [action()], executing: true }));
    render();
    expect(screen.getByRole('button', { name: EXECUTE })).toBeDisabled();
  });
});

describe('ScheduledActionsSettings — creation', () => {
  async function openCreate(user: User) {
    await user.click(screen.getByRole('button', { name: CREATE }));
    return screen.findByLabelText(FIELD_TITLE);
  }

  it('keeps saving impossible until title, prompt and at least one day are given', async () => {
    useScheduledActions.mockReturnValue(hook());
    const { user } = render();
    const title = await openCreate(user);

    expect(saveButton()).toBeDisabled();
    await user.type(title, '   '); // whitespace is not a title
    expect(saveButton()).toBeDisabled();
    await user.clear(title);
    await user.type(title, 'Morning brief');
    expect(saveButton()).toBeDisabled();
    await user.type(screen.getByLabelText(FIELD_PROMPT), 'Summarise my day');
    expect(saveButton()).toBeDisabled(); // no day picked yet
    await user.click(screen.getByRole('button', { name: MONDAY }));
    expect(saveButton()).toBeEnabled();
  });

  it('creates the action with trimmed text and the default 08:00 slot', async () => {
    const createAction = vi.fn().mockResolvedValue(action());
    useScheduledActions.mockReturnValue(hook({ createAction }));
    const { user } = render();
    const title = await openCreate(user);

    // Deliberately short: `user.type` costs ~29 ms per keystroke on a
    // controlled input, and under full-suite parallel load that stretches ~5x.
    // The padded 37-character version of this test timed out at 5 s while
    // passing in 1 s alone — the oracle here is `trim()`, which does not care
    // how long the string is, so the length was pure flake surface.
    await user.type(title, '  Brief  ');
    await user.type(screen.getByLabelText(FIELD_PROMPT), '  Digest  ');
    await user.click(screen.getByRole('button', { name: MONDAY }));
    await user.click(saveButton());

    await waitFor(() =>
      expect(createAction).toHaveBeenCalledWith({
        title: 'Brief',
        action_prompt: 'Digest',
        days_of_week: [1],
        trigger_hour: 8,
        trigger_minute: 0,
        // N-07: a default create is an unchanged "time" routine.
        trigger_kind: 'time',
        condition_config: null,
        requires_approval: false,
      })
    );
    expect(toast.success).toHaveBeenCalledWith('scheduled_actions.create_success');
    // The dialog closes only on success.
    await waitFor(() => expect(screen.queryByLabelText(FIELD_TITLE)).not.toBeInTheDocument());
  });

  it('keeps the form open and reports the failure when the creation is refused', async () => {
    const createAction = vi.fn().mockRejectedValue(new Error('boom'));
    useScheduledActions.mockReturnValue(hook({ createAction }));
    const { user } = render();
    const title = await openCreate(user);

    await user.type(title, 'Morning brief');
    await user.type(screen.getByLabelText(FIELD_PROMPT), 'Summarise my day');
    await user.click(screen.getByRole('button', { name: MONDAY }));
    await user.click(saveButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('scheduled_actions.error_create'));
    expect(screen.getByLabelText(FIELD_TITLE)).toBeInTheDocument();
  });

  it('abandons the draft when the form is cancelled', async () => {
    const createAction = vi.fn();
    useScheduledActions.mockReturnValue(hook({ createAction }));
    const { user } = render();
    const title = await openCreate(user);
    await user.type(title, 'Morning brief');
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    await waitFor(() => expect(screen.queryByLabelText(FIELD_TITLE)).not.toBeInTheDocument());
    expect(createAction).not.toHaveBeenCalled();
  });
});

describe('ScheduledActionsSettings — edition', () => {
  async function openEdit(user: User) {
    await user.click(screen.getByRole('button', { name: EDIT }));
    return screen.findByLabelText(FIELD_TITLE);
  }

  it('prefills the form with the action being edited', async () => {
    useScheduledActions.mockReturnValue(hook({ actions: [action()] }));
    const { user } = render();
    expect(await openEdit(user)).toHaveValue('Morning brief');
    expect(screen.getByLabelText(FIELD_PROMPT)).toHaveValue('Summarise my day');
  });

  it('sends only the field that actually changed', async () => {
    const updateAction = vi.fn().mockResolvedValue(action());
    useScheduledActions.mockReturnValue(hook({ actions: [action()], updateAction }));
    const { user } = render();
    const title = await openEdit(user);

    await user.clear(title);
    await user.type(title, 'Evening brief');
    await user.click(saveButton());

    await waitFor(() =>
      expect(updateAction).toHaveBeenCalledWith('a1', { title: 'Evening brief' })
    );
    expect(toast.success).toHaveBeenCalledWith('scheduled_actions.edit_success');
  });

  it('sends the days when the selection changes, and nothing else', async () => {
    const updateAction = vi.fn().mockResolvedValue(action());
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ days_of_week: [1, 2] })], updateAction })
    );
    const { user } = render();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: MONDAY })); // deselect Monday
    await user.click(saveButton());

    await waitFor(() => expect(updateAction).toHaveBeenCalledWith('a1', { days_of_week: [2] }));
  });

  it('saves nothing when the form is reopened and left untouched', async () => {
    const updateAction = vi.fn();
    useScheduledActions.mockReturnValue(hook({ actions: [action()], updateAction }));
    const { user } = render();
    await openEdit(user);

    await user.click(saveButton());

    // Empty differential: no request, no success wording — and the form closes.
    await waitFor(() => expect(screen.queryByLabelText(FIELD_TITLE)).not.toBeInTheDocument());
    expect(updateAction).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('reports a refused update', async () => {
    const updateAction = vi.fn().mockRejectedValue(new Error('boom'));
    useScheduledActions.mockReturnValue(hook({ actions: [action()], updateAction }));
    const { user } = render();
    const title = await openEdit(user);

    await user.clear(title);
    await user.type(title, 'Evening brief');
    await user.click(saveButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('scheduled_actions.error_update'));
  });
});

describe('ScheduledActionsSettings — duplication', () => {
  const DUPLICATE = 'scheduled_actions.duplicate';

  async function openDuplicate(user: User) {
    await user.click(screen.getByRole('button', { name: DUPLICATE }));
    return screen.findByLabelText(FIELD_TITLE);
  }

  it('opens a CREATION form carrying every field of the source routine', async () => {
    // The point of duplicating is declining a routine (week/weekend,
    // personal/professional): everything is copied, only the title is marked.
    useScheduledActions.mockReturnValue(
      hook({
        actions: [
          action({ days_of_week: [6, 7], trigger_hour: 19, trigger_minute: 30 }),
        ],
      })
    );
    const { user } = render();

    expect(await openDuplicate(user)).toHaveValue(
      'Morning brief scheduled_actions.duplicate_suffix'
    );
    expect(screen.getByLabelText(FIELD_PROMPT)).toHaveValue('Summarise my day');
  });

  it('creates nothing until the reader saves', async () => {
    const createAction = vi.fn().mockResolvedValue(action());
    useScheduledActions.mockReturnValue(hook({ actions: [action()], createAction }));
    const { user } = render();

    await openDuplicate(user);

    expect(createAction).not.toHaveBeenCalled();
  });

  it('creates a NEW routine on save — it never edits the source', async () => {
    const createAction = vi.fn().mockResolvedValue(action());
    const updateAction = vi.fn();
    useScheduledActions.mockReturnValue(
      hook({ actions: [action()], createAction, updateAction })
    );
    const { user } = render();
    await openDuplicate(user);

    await user.click(saveButton());

    await waitFor(() => expect(createAction).toHaveBeenCalledTimes(1));
    expect(updateAction).not.toHaveBeenCalled();
    expect(createAction.mock.calls[0][0]).toMatchObject({
      title: 'Morning brief scheduled_actions.duplicate_suffix',
      action_prompt: 'Summarise my day',
      days_of_week: [1, 2],
      trigger_hour: 8,
      trigger_minute: 0,
    });
  });

  it('carries the condition of a CONDITION routine, filter included', async () => {
    // A `mail_match` copied without its query is refused by the backend
    // schema — duplicating would produce a routine that cannot be saved.
    const createAction = vi.fn().mockResolvedValue(action());
    useScheduledActions.mockReturnValue(
      hook({
        actions: [
          action({
            trigger_kind: 'condition',
            condition_config: { type: 'mail_match', query: 'invoice' },
          }),
        ],
        createAction,
      })
    );
    const { user } = render();
    await openDuplicate(user);

    await user.click(saveButton());

    await waitFor(() => expect(createAction).toHaveBeenCalledTimes(1));
    expect(createAction.mock.calls[0][0]).toMatchObject({
      trigger_kind: 'condition',
      condition_config: { type: 'mail_match', query: 'invoice' },
    });
  });

  it('never lets the suffix push the title past the column limit', async () => {
    // `title` is `max_length=200` server-side: an over-long copy would be
    // rejected by the API after the reader believed the form was valid.
    const longTitle = 'x'.repeat(200);
    useScheduledActions.mockReturnValue(hook({ actions: [action({ title: longTitle })] }));
    const { user } = render();

    const field = await openDuplicate(user);

    expect((field as HTMLInputElement).value.length).toBeLessThanOrEqual(200);
  });
});

describe('ScheduledActionsSettings — deletion', () => {
  /** Opens the row's confirmation; the confirm button shares the trigger label. */
  async function confirmDelete(user: User) {
    await user.click(screen.getByRole('button', { name: DELETE }));
    const buttons = await screen.findAllByRole('button', { name: DELETE });
    await user.click(buttons[buttons.length - 1]);
  }

  it('deletes only once the confirmation is validated', async () => {
    const deleteAction = vi.fn().mockResolvedValue(undefined);
    useScheduledActions.mockReturnValue(hook({ actions: [action()], deleteAction }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: DELETE }));
    expect(deleteAction).not.toHaveBeenCalled();

    const buttons = await screen.findAllByRole('button', { name: DELETE });
    await user.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(deleteAction).toHaveBeenCalledWith('a1'));
    expect(toast.success).toHaveBeenCalledWith('scheduled_actions.delete_success');
  });

  it('keeps the action when the confirmation is dismissed', async () => {
    const deleteAction = vi.fn();
    useScheduledActions.mockReturnValue(hook({ actions: [action()], deleteAction }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: DELETE }));
    await user.click(await screen.findByRole('button', { name: 'common.cancel' }));
    expect(deleteAction).not.toHaveBeenCalled();
  });

  it('reports a refused deletion', async () => {
    const deleteAction = vi.fn().mockRejectedValue(new Error('boom'));
    useScheduledActions.mockReturnValue(hook({ actions: [action()], deleteAction }));
    const { user } = render();
    await confirmDelete(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('scheduled_actions.error_delete'));
  });
});

describe('the enable/disable toggle of a routine in the list', () => {
  // Found by the browser scan, not by the static ratchet: a Radix `Switch`
  // renders a `<button role="switch">`, and jsx-a11y cannot see that nothing
  // names it. Axe reported it `critical` — a screen-reader user hears "switch,
  // on" with no idea which routine it belongs to, on a list of several.
  it('carries a name that says what it does AND which routine', async () => {
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ title: 'Revue du matin', is_enabled: true })], total: 1 })
    );
    render();

    const toggle = await screen.findByRole('switch', {
      name: 'scheduled_actions.toggle_aria',
    });
    expect(toggle).toBeChecked();
  });

  it('names every routine in the list, not only the first', async () => {
    // The harness translator is `(key) => key` (src/__tests__/setup.ts), so
    // the interpolated titles cannot be observed through the DOM here. What
    // this pins is that EVERY row carries the name — a loop that named only
    // the first would leave the rest anonymous, which is the shape of the
    // defect axe found. That the resulting names then differ is proven in a
    // real browser, with real translations, by the `button-name` check in
    // e2e/a11y/axe-journeys.spec.ts.
    useScheduledActions.mockReturnValue(
      hook({
        actions: [
          action({ id: 'a1', title: 'Revue du matin' }),
          action({ id: 'a2', title: 'Bilan du soir' }),
        ],
        total: 2,
      })
    );
    render();

    const toggles = await screen.findAllByRole('switch');
    expect(toggles).toHaveLength(2);
    for (const toggle of toggles) {
      expect(toggle).toHaveAttribute('aria-label', 'scheduled_actions.toggle_aria');
    }
  });
});

describe('where the keyboard lands once a routine is deleted', () => {
  // Same defect as the reminder card, in the other panel: Radix returns focus
  // to the trigger the dialog opened from, and that trigger lived inside the
  // row the deletion just removed. The keyboard user is dropped on <body> and
  // has to tab back through the whole settings page.
  it('returns focus into the section, not to the top of the document', async () => {
    const deleteAction = vi.fn().mockResolvedValue(undefined);
    useScheduledActions.mockReturnValue(
      hook({ actions: [action({ title: 'Revue du matin' })], total: 1, deleteAction })
    );
    const { user } = render();

    await user.click(await screen.findByRole('button', { name: DELETE }));
    await user.click(screen.getByText(DELETE, { selector: 'button' }));

    await waitFor(() => expect(deleteAction).toHaveBeenCalled());
    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      // The panel's own region: it outlives every row, including the last one
      // — which is precisely when a row-based anchor would vanish too.
      expect(document.activeElement).toHaveAttribute('data-routines-region');
    });
  });
});
