import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import apiClient from '@/lib/api-client';
import type { JevCallTrace } from '@/types/jev';
import { DebugPanel } from '../DebugPanel';

const trace: JevCallTrace = {
  id: 'call-1',
  run_id: 'meeting-run',
  caller: 'meeting_template_selection',
  usage: 'meeting_template',
  started_at: '2026-09-28T15:00:00Z',
  requested_model: 'jev-1.13.0',
  reported_model: 'jev-1.13.0',
  duration_ms: 251,
  context: {
    text: '<script>alert(1)</script> synthetic context',
    original_characters: 10000,
    omitted_characters: 4000,
  },
  response: {
    choice: 'c1',
    choice_label: 'Medical consultation',
    confidence: 0.99,
    probabilities: [{ key: 'c1', label: 'Medical consultation', probability: 0.999 }],
    omitted_candidates: 11,
  },
  outcome: 'success',
  action: 'selected',
  action_target: 'builtin:medical',
  input_tokens: 300,
  output_tokens: 2,
  cost_eur: 0.000011,
  status_code: null,
};
const page = { calls: [trace], limit: 30, retention_seconds: 3600 };
const key = (name: string) => `chat.debug_panel.jev.${name}`;

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.useRealTimers());

describe('JEV debug feed independent of chat turns', () => {
  it('keeps native Choice separate from an empty proposal for new memory writes', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          action: 'observed',
          usage: 'observe_memory',
          observed_result: { text: ' [] ', original_characters: 4, omitted_characters: 0 },
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('memoryEmptyProposal'))).toBeVisible();
    expect(screen.getByText(key('memoryObservationHelp'))).toBeVisible();
    expect(screen.getByText(key('observedResultHelp'))).toBeVisible();
    expect(screen.getByText('Medical consultation')).toBeVisible();
    const native = screen.getByRole('heading', { name: key('response') });
    expect(native.compareDocumentPosition(screen.getByText(key('observedResult')))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
    await user.click(screen.getByText(key('observedResult')));
    expect(screen.getByRole('region', { name: key('observedResult') })).toHaveTextContent('[]');
    expect(screen.queryByText(key('noResponse'))).not.toBeInTheDocument();
  });

  it.each([
    { text: '[]', omitted: 1, usage: 'observe_memory' },
    { text: '"[]"', omitted: 0, usage: 'observe_memory' },
    { text: '[', omitted: 0, usage: 'observe_memory' },
    { text: '[{"fact":"Synthetic fact"}]', omitted: 0, usage: 'observe_memory' },
    { text: '[]', omitted: 0, usage: 'observe_interests' },
  ])('does not infer an empty memory proposal from $usage / $text / $omitted', async item => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          action: 'observed',
          usage: item.usage,
          observed_result: {
            text: item.text,
            original_characters: item.text.length + item.omitted,
            omitted_characters: item.omitted,
          },
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('observedResultHelp'))).toBeVisible();
    expect(screen.queryByText(key('memoryEmptyProposal'))).not.toBeInTheDocument();
    await user.click(screen.getByText(key('observedResult')));
    expect(screen.getByRole('region', { name: key('observedResult') })).toHaveTextContent(item.text);
  });

  it('shows global collection coverage without treating unsubmitted candidates as unknown', async () => {
    const coverage = {
      candidate_count: 75,
      evaluated_count: 14,
      unevaluated_count: 61,
      unknown_count: 14,
      omitted_count: 0,
      batch_count: 2,
    };
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [1, 2].map(index => ({
        ...trace,
        id: `batch-${index}`,
        usage: 'filter_event',
        action: 'preview',
        collection_coverage: { ...coverage, batch_index: index },
      })),
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    await screen.findAllByRole('heading', { name: key('coverageTitle') });
    for (const article of screen.getAllByRole('article')) {
      const query = within(article);
      expect(query.getByText(key('coverageCandidates')).nextElementSibling).toHaveTextContent('75');
      expect(query.getByText(key('coverageEvaluated')).nextElementSibling).toHaveTextContent('14');
      expect(query.getByText(key('coverageUnevaluated')).nextElementSibling).toHaveTextContent('61');
      expect(query.getByText(key('coverageUnknown')).nextElementSibling).toHaveTextContent('14');
      expect(query.getByText(key('coverageOmitted')).nextElementSibling).toHaveTextContent('0');
      expect(query.getByText(key('coverageBatch'))).toBeVisible();
      expect(query.getByText(key('coverageSharedHelp'))).toBeVisible();
    }
    expect(screen.queryByText(key('coverageUnavailable'))).not.toBeInTheDocument();
  });

  it('keeps absent historical coverage unavailable rather than counting displayed answers', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [{ ...trace, usage: 'filter_email', action: 'preview' }],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('coverageUnavailable'))).toBeVisible();
    expect(screen.queryByText(key('coverageCandidates'))).not.toBeInTheDocument();
    expect(screen.queryByText(key('observedResultHelp'))).not.toBeInTheDocument();
    expect(screen.queryByText(key('memoryEmptyProposal'))).not.toBeInTheDocument();
  });

  it('distinguishes observation from action and exposes the bounded baseline proposal safely', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          action: 'observed',
          usage: 'observe_memory',
          observed_result: {
            text: '<img src=x onerror=alert(1)> original proposal',
            original_characters: 10000,
            omitted_characters: 4000,
          },
        },
      ],
    });
    const { user, container } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('actionHelp.observed'))).toBeVisible();
    await user.click(screen.getByText(key('observedResult')));
    expect(screen.getByText(/original proposal/)).toBeVisible();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getAllByText(key('truncated')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(key('contextDisplayHelp'))).toHaveLength(1);
    expect(screen.queryByText(key('actions.selected'))).not.toBeInTheDocument();
  });
  it('names the source object and distinguishes JEV suggestion from LIA applied verdict', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          action: 'preview',
          response: null,
          responses: {
            q0: { ...trace.response, choice: 'non_match', choice_label: 'Proposed exclusion' },
          },
          applied_decisions: { q0: 'unknown' },
          decision_labels: { q0: 'Project meeting' },
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText('Project meeting')).toBeVisible();
    expect(screen.getByText('Proposed exclusion')).toBeVisible();
    expect(screen.getByText(key('appliedDecision'))).toBeVisible();
    expect(screen.getByText(key('actions.preview'))).toBeVisible();
  });
  it('keeps a retained preview trace distinct from an applied action after an upgrade', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [{ ...trace, action: 'selected', action_target: 'result_preview' }],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('actions.preview'))).toBeVisible();
    expect(screen.getByText(key('actionHelp.preview'))).toBeVisible();
    expect(screen.queryByText(key('actions.selected'))).not.toBeInTheDocument();
  });
  it('leads with the translated purpose and action, keeping technical identifiers in details', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(page);
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(
      await screen.findByRole('heading', { name: 'settings.admin.jev.usages.meeting_template' })
    ).toBeVisible();
    expect(screen.getByText(key('actionHelp.selected'))).toBeVisible();
    expect(screen.getByText(key('nativeDuration'))).toBeVisible();
    expect(screen.getByText('meeting-run')).not.toBeVisible();
    await user.click(screen.getByText(key('technical')));
    expect(screen.getByText('meeting-run')).toBeVisible();
  });

  it('renders complete JSON context as readable fields without interpreting external HTML', async () => {
    const content = '<img src=x onerror=alert(1)>\nSecond line';
    const context = JSON.stringify({
      state: { query: content },
      question: { query: 'Choose?', criteria: { yes: 'Yes' } },
    });
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          context: { text: context, original_characters: context.length, omitted_characters: 0 },
        },
      ],
    });
    const { user, container } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    await user.click(await screen.findByText(key('context')));
    expect(screen.getAllByText('query')).toHaveLength(2);
    expect(screen.getByText(/Second line/)).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(key('question'))).toBeVisible();
  });
  it('formats every batch decision while displaying its shared cost once', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          response: null,
          responses: {
            q0: { ...trace.response, choice: 'match', choice_label: 'Relevant' },
            q1: { ...trace.response, choice: 'unknown', choice_label: 'Insufficient evidence' },
          },
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText('Relevant')).toBeInTheDocument();
    expect(screen.getByText('Insufficient evidence')).toBeInTheDocument();
    expect(screen.getByText('q0')).toBeInTheDocument();
    expect(screen.getByText('q1')).toBeInTheDocument();
    expect(screen.getAllByText(key('cost'))).toHaveLength(1);
  });
  it('shows a provider failure without inventing a response or spend', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          response: null,
          reported_model: null,
          input_tokens: null,
          output_tokens: null,
          cost_eur: null,
          status_code: 503,
          action: 'fallback',
          outcome: 'provider_error',
          action_target: 'meeting_synthesis',
          context: { text: 'short context', original_characters: 13, omitted_characters: 0 },
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('noResponse'))).toBeInTheDocument();
    expect(screen.getByText('provider_error · HTTP 503')).toBeInTheDocument();
    expect(screen.getByText(key('unknownCost'))).toBeVisible();
    expect(screen.queryByText(key('truncated'))).not.toBeInTheDocument();
  });

  it('shows a bounded validation reason in technical details and preserves the paid fallback', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...page,
      calls: [
        {
          ...trace,
          response: null,
          action: 'fallback',
          outcome: 'invalid_response',
          invalid_response_reason: 'probability_sum',
          action_target: 'meeting_synthesis',
        },
      ],
    });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('actions.fallback'))).toBeVisible();
    expect(screen.getByText(key('noResponse'))).toBeVisible();
    await user.click(screen.getByText(key('technical')));
    expect(screen.getByText('invalid_response · probability_sum')).toBeVisible();
    expect(screen.getByText('300 / 2')).toBeVisible();
    expect(screen.queryByText(key('unknownCost'))).not.toBeInTheDocument();
  });

  it('retains opened details while a refresh updates the same call action', async () => {
    const get = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({
        ...page,
        calls: [
          {
            ...trace,
            action: 'pending',
            action_target: null,
            reported_model: 'unexpected-model',
            output_tokens: null,
          },
        ],
      })
      .mockResolvedValue(page);
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    expect(await screen.findByText(key('actions.pending'))).toBeInTheDocument();
    expect(screen.getByText('jev-1.13.0 → unexpected-model')).toBeInTheDocument();
    const context = screen.getByText(key('context'));
    await user.click(context);
    expect(context.closest('details')).toHaveAttribute('open');
    await user.click(screen.getByRole('button', { name: key('refresh') }));
    expect(await screen.findByText(key('actions.selected'))).toBeInTheDocument();
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(context.closest('details')).toHaveAttribute('open');
    expect(get).toHaveBeenCalledTimes(2);
  });
  it('only reads after opening, renders escaped context and the chosen branch, and cancels on close', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(page);
    const { user, container } = renderWithProviders(<DebugPanel metrics={null} />);
    const toggle = screen.getByRole('button', { name: key('title') });
    expect(get).not.toHaveBeenCalled();
    await user.click(toggle);
    expect(await screen.findByText('meeting_template_selection')).toBeInTheDocument();
    expect(screen.getByText(trace.context.text)).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(key('truncated'))).toBeInTheDocument();
    expect(screen.getByText(key('actions.selected'))).toBeInTheDocument();
    expect(screen.getByText('builtin:medical')).toBeInTheDocument();
    expect(screen.getByText(key('omittedCandidates'))).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      '/debug/jev',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    await user.click(toggle);
    expect(screen.queryByText(trace.context.text)).not.toBeInTheDocument();
    get.mockResolvedValue({ ...page, calls: [] });
    await user.click(toggle);
    expect(await screen.findByText(key('empty'))).toBeInTheDocument();
    expect(screen.queryByText(trace.context.text)).not.toBeInTheDocument();
  });

  it('clears private data on a refused refresh, recovers and preserves keyboard focus', async () => {
    const get = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce(page)
      .mockRejectedValueOnce(new Error('denied'))
      .mockResolvedValue({ ...page, calls: [] });
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    await user.click(screen.getByRole('button', { name: key('title') }));
    await screen.findByText(trace.context.text);
    const refresh = screen.getByRole('button', { name: key('refresh') });
    refresh.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent(key('error'));
    expect(screen.queryByText(trace.context.text)).not.toBeInTheDocument();
    expect(refresh).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(await screen.findByText(key('empty'))).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('does not duplicate a pending read on refresh and aborts it when the section closes', async () => {
    const get = vi.spyOn(apiClient, 'get').mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<DebugPanel metrics={null} />);
    const toggle = screen.getByRole('button', { name: key('title') });
    await user.click(toggle);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const signal = get.mock.calls[0][1]?.signal;
    await user.click(screen.getByRole('button', { name: key('refresh') }));
    expect(get).toHaveBeenCalledTimes(1);
    await user.click(toggle);
    expect(signal?.aborted).toBe(true);
  });
});
