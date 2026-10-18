import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/__tests__/test-utils';
import { makeMessage, makePsycheState } from '@/__tests__/factories';
import { useLiaGender } from '@/hooks/useLiaGender';
import { usePsycheStore } from '@/stores/psycheStore';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import {
  EYE_STYLE_IDS,
  HYBRID_EYE_STYLE_IDS,
  isRigEyeStyle,
  type EyeStyleId,
} from '@/components/eyes/eye-styles';
import type { SpiritExpression, SpiritVariant } from '@/components/spirit/catalogue';
import type { PsycheStateSummary } from '@/types/psyche';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';
import { ChatMessageList } from '../ChatMessageList';
import { companionBodyAsset } from '@/components/spirit/companion-catalogue';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: vi.fn() }) }));

const snapshot: PsycheStateSummary = {
  mood_label: 'melancholic',
  mood_color: '#818cf8',
  mood_pleasure: -0.5,
  mood_arousal: -0.2,
  mood_dominance: -0.1,
  active_emotion: null,
  emotion_intensity: 0,
  relationship_stage: 'ORIENTATION',
};
const messages = [
  makeMessage({
    id: 'past',
    role: 'assistant',
    content: 'Earlier answer',
    metadata: { psyche_state: snapshot },
  }),
  makeMessage({
    id: 'latest',
    role: 'assistant',
    content: 'Latest answer',
    metadata: { psyche_state: { ...snapshot, mood_label: 'curious' } },
  }),
];

let psycheEnabled = true;
let browser: ReturnType<typeof installSpiritBrowser>;

beforeEach(() => {
  document.cookie = 'lia_gender=female; path=/';
  browser = installSpiritBrowser();
  psycheEnabled = true;
  useEyesWidgetStore.getState().setStyle('spirit');
  usePsycheStore.getState().reset();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const endpoint = String(input);
      if (endpoint.endsWith('/psyche/state')) return Response.json(makePsycheState());
      if (endpoint.endsWith('/psyche/settings'))
        return Response.json({
          psyche_enabled: psycheEnabled,
          psyche_display_avatar: true,
          psyche_sensitivity: 50,
          psyche_stability: 50,
        });
      throw new Error(`Unexpected API read: ${endpoint}`);
    })
  );
});
afterEach(() => {
  cleanup();
  useEyesWidgetStore.getState().reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.cookie = 'lia_gender=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});

async function renderConversation(controls = false) {
  return act(async () =>
    renderWithProviders(
      <>
        {controls && <GenderChoice />}
        <ChatMessageList messages={messages} />
      </>
    )
  );
}

function GenderChoice() {
  const { setGender } = useLiaGender();
  return (
    <>
      <button onClick={() => setGender(true)}>Select masculine LIA</button>
      <button onClick={() => setGender(false)}>Select feminine LIA</button>
    </>
  );
}

function historyPortrait(
  row: HTMLElement,
  style: EyeStyleId,
  variant: SpiritVariant,
  expression: SpiritExpression
) {
  const face = row.querySelector('.lia-eyes');
  expect(face).toHaveAttribute('data-expression', expression);
  expect(face).toHaveAttribute('data-motion', 'off');
  expect(face).toHaveAttribute('data-life', 'off');
  expect(row.querySelector('canvas')).toBeNull();
  if (isRigEyeStyle(style)) {
    expect(face).toHaveAttribute('data-style', style);
    if (style === 'smiley') expect(face).toHaveAttribute('data-smiley-variant', variant);
    else expect(row.querySelector('.lia-monitor-screen')).not.toBeNull();
  } else {
    const body = row.querySelector(`[data-character="${style}"]`);
    expect(body).toHaveAttribute('data-spirit-companion', variant);
    expect(body).toHaveStyle({
      '--spirit-body-url': `url('${companionBodyAsset(style, variant)}')`,
    });
  }
}

function showNativePortrait(row: HTMLElement, visible = true) {
  const target = row.querySelector('[data-companion-portrait]');
  if (!target) throw new Error('Native portrait visibility target missing');
  const observer = SpiritIntersectionObserver.instances.find(instance =>
    instance.targets.has(target)
  );
  if (!observer) throw new Error('Native portrait has no shared visibility observer');
  observer.notify(target, visible);
}

describe('Chat portrait identity and emotional history', () => {
  it('uses the chosen masculine variant for every row but animates only the latest', async () => {
    document.cookie = 'lia_gender=male; path=/';
    const { container } = await renderConversation();
    const past = container.querySelector<HTMLElement>('[data-message-id="past"]')!;
    const latest = container.querySelector<HTMLElement>('[data-message-id="latest"]')!;
    act(() => {
      showNativePortrait(past);
      showNativePortrait(latest);
    });
    historyPortrait(past, 'spirit', 'male', 'sad');
    const liveFace = latest.querySelector<HTMLElement>('.lia-eyes')!;
    const rigObserver = SpiritIntersectionObserver.instances.find(instance =>
      instance.targets.has(liveFace)
    );
    if (!rigObserver) throw new Error('The live portrait must have its native visibility owner');
    act(() => rigObserver.notify(liveFace, true));
    expect(liveFace).toHaveAttribute('data-rig-visible', 'true');
    expect(liveFace).toHaveAttribute('data-expression', 'attentive');
    expect(liveFace).not.toHaveAttribute('data-motion', 'off');
    expect(latest.querySelector('[data-character="spirit"]')).toHaveAttribute(
      'data-spirit-companion',
      'male'
    );
    expect(latest.querySelectorAll('[data-volume-canvas]')).toHaveLength(1);
    expect(container.querySelectorAll('canvas')).toHaveLength(1);
    expect(container.querySelectorAll('img')).toHaveLength(0);
    expect(activeFrameSubscribers()).toBe(1);
    act(() => showNativePortrait(latest, false));
    historyPortrait(past, 'spirit', 'male', 'sad');
    historyPortrait(latest, 'spirit', 'male', 'attentive');
    expect(container.querySelectorAll('canvas')).toHaveLength(0);
    expect(rigObserver.targets.has(liveFace)).toBe(false);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('keeps historical moods after a live update and follows the shared identity choice', async () => {
    const { container, getByRole } = await renderConversation(true);
    act(() => usePsycheStore.getState().updateFromSSE({ ...snapshot, mood_label: 'energized' }));
    fireEvent.click(getByRole('button', { name: 'Select masculine LIA' }));
    historyPortrait(
      container.querySelector<HTMLElement>('[data-message-id="past"]')!,
      'spirit',
      'male',
      'sad'
    );
    historyPortrait(
      container.querySelector<HTMLElement>('[data-message-id="latest"]')!,
      'spirit',
      'male',
      'attentive'
    );
  });

  it('follows each selected avatar in already mounted memoized history without replacing its mood', async () => {
    const { container } = await renderConversation();
    const past = container.querySelector<HTMLElement>('[data-message-id="past"]')!;
    act(() => usePsycheStore.getState().updateFromSSE({ ...snapshot, mood_label: 'energized' }));
    for (const style of EYE_STYLE_IDS) {
      act(() => useEyesWidgetStore.getState().setStyle(style));
      expect(container.querySelector('[data-message-id="past"]')).toBe(past);
      historyPortrait(past, style, 'female', 'sad');
    }
    expect(messages[0].metadata?.psyche_state).toEqual(snapshot);
  });

  it('changes Smiley and hybrid identities immediately while preserving both saved message expressions', async () => {
    const { container, getByRole } = await renderConversation(true);
    const past = container.querySelector<HTMLElement>('[data-message-id="past"]')!;
    const latest = container.querySelector<HTMLElement>('[data-message-id="latest"]')!;
    for (const style of ['smiley', ...HYBRID_EYE_STYLE_IDS] satisfies EyeStyleId[]) {
      act(() => useEyesWidgetStore.getState().setStyle(style));
      fireEvent.click(getByRole('button', { name: 'Select masculine LIA' }));
      historyPortrait(past, style, 'male', 'sad');
      historyPortrait(latest, style, 'male', 'attentive');
      fireEvent.click(getByRole('button', { name: 'Select feminine LIA' }));
      historyPortrait(past, style, 'female', 'sad');
      historyPortrait(latest, style, 'female', 'attentive');
    }
  });

  it('hides a past answer’s mood once « Show emotional avatar » is off', async () => {
    // The switch used to gate the live fallback alone: every finished answer
    // kept the mood stored with it, whatever the person had chosen.
    act(() => usePsycheStore.getState().setDisplayAvatar(false));
    document.cookie = 'lia_gender=male; path=/';
    useEyesWidgetStore.getState().setStyle('smiley');
    const { container } = await renderConversation();
    const past = container.querySelector<HTMLElement>('[data-message-id="past"]')!;
    await waitFor(() => historyPortrait(past, 'smiley', 'male', 'neutral'));
  });

  it('shows the selected neutral portrait when psyche is disabled and the message has no snapshot', async () => {
    psycheEnabled = false;
    document.cookie = 'lia_gender=male; path=/';
    useEyesWidgetStore.getState().setStyle('smiley');
    const plainMessage = makeMessage({ id: 'plain', role: 'assistant', metadata: {} });
    const { container } = await act(async () =>
      renderWithProviders(<ChatMessageList messages={[plainMessage]} />)
    );
    const row = container.querySelector<HTMLElement>('[data-message-id="plain"]')!;
    await waitFor(() => historyPortrait(row, 'smiley', 'male', 'neutral'));
  });

  it('wakes only a visible live or hovered miniature and drops its canvas on suspension', async () => {
    useEyesWidgetStore.getState().setStyle('smiley');
    const { container } = await renderConversation();
    const past = container.querySelector<HTMLElement>('[data-message-id="past"]')!;
    const latest = container.querySelector<HTMLElement>('[data-message-id="latest"]')!;
    historyPortrait(past, 'smiley', 'female', 'sad');
    historyPortrait(latest, 'smiley', 'female', 'attentive');

    act(() => showNativePortrait(past));
    historyPortrait(past, 'smiley', 'female', 'sad');
    act(() => showNativePortrait(latest));
    expect(latest.querySelector('.lia-eyes')).not.toHaveAttribute('data-motion', 'off');
    expect(container.querySelectorAll('canvas')).toHaveLength(1);

    act(() => browser.setVisibility('hidden'));
    expect(container.querySelectorAll('canvas')).toHaveLength(0);
    act(() => browser.setVisibility('visible'));
    expect(container.querySelectorAll('canvas')).toHaveLength(1);
    act(() => showNativePortrait(latest, false));
    historyPortrait(latest, 'smiley', 'female', 'attentive');

    act(() => browser.setMotion(true));
    const hoverTarget = past.querySelector<HTMLElement>('[role="presentation"]')!;
    fireEvent.mouseEnter(hoverTarget);
    historyPortrait(past, 'smiley', 'female', 'sad');
    act(() => browser.setMotion(false));
    expect(past.querySelector('.lia-eyes')).not.toHaveAttribute('data-motion', 'off');
    expect(container.querySelectorAll('canvas')).toHaveLength(1);
    fireEvent.mouseLeave(hoverTarget);
    historyPortrait(past, 'smiley', 'female', 'sad');
    expect(container.querySelectorAll('canvas')).toHaveLength(0);
  });
});
