/**
 * The answer's place in a detail (ADR-372): nothing at all until it is asked for, a shape while it
 * comes, what it cost beside the words, and a way out at every moment.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { LLMUsage } from '@/types/llm-usage';

import { AssistPanel, HeardWords, VoiceCost } from '../AssistPanel';
import type { AssistCall, AssistState } from '@/hooks/useAssistCall';

interface Answer {
  text: string;
  usage: LLMUsage | null;
}

function callIn(state: AssistState<Answer>): AssistCall<Answer> {
  return { state, run: vi.fn(), stop: vi.fn(), retry: vi.fn() };
}

function draw(state: AssistState<Answer>) {
  const call = callIn(state);
  const rendered = renderWithProviders(
    <AssistPanel lng="en" title="Summary" call={call}>
      {answer => <p>{answer.text}</p>}
    </AssistPanel>
  );
  return { ...rendered, call };
}

const COST: LLMUsage = {
  tokens_in: 10,
  tokens_out: 5,
  tokens_cache: 0,
  cost_eur: 0.001,
  model_name: null,
};

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe('AssistPanel — a voice', () => {
  const HEARD = { audio: 'SUQz', cut: false, cost_eur: 0.002, usage: null };
  it('keeps a playable source through Strict Mode and replaces it when the answer changes', () => {
    const { rerender } = renderWithProviders(
      <HeardWords lng="en" label="Read aloud" answer={HEARD} />,
      { reactStrictMode: true }
    );
    const player = screen.getByLabelText<HTMLAudioElement>('Read aloud');
    expect(player).toHaveAttribute('src', 'data:audio/mpeg;base64,SUQz');
    rerender(<HeardWords lng="en" label="Read aloud" answer={{ ...HEARD, audio: 'bmV3' }} />);
    expect(player).toHaveAttribute('src', 'data:audio/mpeg;base64,bmV3');
  });

  it('releases an audio request even while its metadata is loading', () => {
    const { unmount } = renderWithProviders(
      <HeardWords lng="en" label="Read aloud" answer={HEARD} />
    );
    const player = screen.getByLabelText<HTMLAudioElement>('Read aloud');
    Object.defineProperty(player, 'networkState', {
      configurable: true,
      value: HTMLMediaElement.NETWORK_LOADING,
    });
    const load = vi.spyOn(player, 'load').mockImplementation(() => {});
    expect(player.readyState).toBe(0);
    unmount();
    expect(load).toHaveBeenCalledOnce();
  });
  it('releases the current audio when its bubble closes', () => {
    const { unmount } = renderWithProviders(
      <HeardWords lng="en" label="Read aloud" answer={HEARD} />
    );
    const player = screen.getByLabelText<HTMLAudioElement>('Read aloud');
    const pause = vi.spyOn(player, 'pause').mockImplementation(() => {});
    const load = vi.spyOn(player, 'load').mockImplementation(() => {});
    Object.defineProperty(player, 'paused', { configurable: true, value: false });
    Object.defineProperty(player, 'readyState', { configurable: true, value: 1 });
    unmount();
    expect(pause).toHaveBeenCalledOnce();
    expect(load).toHaveBeenCalledOnce();
    expect(player).not.toHaveAttribute('src');
  });

  it('gives the person a player they hold, and says when only the beginning is read', () => {
    const { rerender } = renderWithProviders(
      <HeardWords lng="en" label="Read aloud" answer={HEARD} />
    );

    const player = screen.getByLabelText('Read aloud');
    expect(player).toHaveAttribute('controls');
    expect(player).toHaveAttribute('src', 'data:audio/mpeg;base64,SUQz');
    expect(screen.queryByText('workbench.assist.voice.read_cut')).toBeNull();

    rerender(<HeardWords lng="en" label="Read aloud" answer={{ ...HEARD, cut: true }} />);
    expect(screen.getByText('workbench.assist.voice.read_cut')).toBeInTheDocument();
  });

  it('says what the voice cost in place of tokens, and nothing of a free engine', () => {
    const call: AssistCall<Answer> = callIn({
      status: 'done',
      value: { text: 'Heard', usage: null },
    });
    renderWithProviders(
      <AssistPanel lng="en" title="Read aloud" call={call} spent={() => <p>Cost line</p>}>
        {answer => <p>{answer.text}</p>}
      </AssistPanel>
    );
    expect(screen.getByText('Cost line')).toBeInTheDocument();
    expect(screen.queryByText('workbench.assist.held')).toBeNull();

    const { container } = renderWithProviders(<VoiceCost lng="en" cost={0} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AssistPanel', () => {
  it('takes no room before anything is asked', () => {
    const { container } = draw({ status: 'idle' });

    expect(container).toBeEmptyDOMElement();
  });

  it('says it is reading, and can be left', async () => {
    const { user, call } = draw({ status: 'running' });

    expect(screen.getByRole('status')).toHaveTextContent('workbench.assist.reading');
    await user.click(screen.getByRole('button', { name: 'workbench.assist.close' }));

    expect(call.stop).toHaveBeenCalledTimes(1);
  });

  it('gives the focus back to the icon it was asked from', async () => {
    const call = callIn({ status: 'done', value: { text: 'The gist', usage: null } });
    const { user } = renderWithProviders(
      <div>
        <button data-assist-trigger="true">Stars</button>
        <div>
          <AssistPanel lng="en" title="Summary" call={call}>
            {answer => <p>{answer.text}</p>}
          </AssistPanel>
        </div>
      </div>
    );

    await user.click(screen.getByRole('button', { name: 'workbench.assist.close' }));

    expect(screen.getByRole('button', { name: 'Stars' })).toHaveFocus();
  });

  it('draws the answer and what it cost beside it', () => {
    draw({ status: 'done', value: { text: 'The gist', usage: COST } });

    expect(screen.getByText('The gist')).toBeInTheDocument();
    expect(screen.getByText(/common\.llm_usage\.tokens/)).toBeInTheDocument();
    expect(screen.queryByText('workbench.assist.held')).toBeNull();
  });

  it('says an answer already held cost nothing now, and invents no figure', () => {
    draw({ status: 'done', value: { text: 'The gist', usage: null } });

    expect(screen.getByText('workbench.assist.held')).toBeInTheDocument();
    expect(screen.queryByText(/common\.llm_usage\.tokens/)).toBeNull();
  });

  it('tells a refusal and offers to ask again', async () => {
    const { user, call } = draw({
      status: 'failed',
      refusal: { key: 'workbench.errors.assist_failed' },
    });

    expect(screen.getByRole('alert')).toHaveTextContent('workbench.errors.assist_failed');
    await user.click(screen.getByRole('button', { name: 'workbench.states.retry' }));

    expect(call.retry).toHaveBeenCalledTimes(1);
  });

  it('says it failed even when nothing named why', () => {
    draw({ status: 'failed', refusal: null });

    expect(screen.getByRole('alert')).toHaveTextContent('workbench.assist.failed');
  });

  it('comes into view when it opens: the person may have scrolled down the message', () => {
    draw({ status: 'running' });

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
  });

  it('names its region for the ear', () => {
    draw({ status: 'running' });

    expect(screen.getByRole('region', { name: 'Summary' })).toBeInTheDocument();
  });
});
