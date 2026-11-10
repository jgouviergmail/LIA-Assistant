import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent } from '@testing-library/react';
import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import apiClient from '@/lib/api-client';
import type { JevSettings, JevStatisticsResponse, JevUsageStatus } from '@/types/jev';
import AdminJevSection from '../AdminJevSection';

const endpoint = '/admin/llm-config/jev';
const localLabel = 'settings.admin.jev.usages.meeting_template';
const globalLabel = 'settings.admin.jev.globalLabel';
function settings(over: Partial<JevSettings> = {}): JevSettings {
  return {
    enabled: false,
    usages: [
      {
        usage: 'meeting_template',
        label_key: localLabel,
        llm_type: 'meeting_template_selection',
        enabled: true,
        effective: false,
        readiness: 'ready',
        gates: [],
        qualified: true,
      },
    ],
    ...over,
  };
}

const thresholdsEndpoint = '/admin/llm-config/jev/thresholds';
const statisticsEndpoint = '/admin/llm-config/jev/statistics?days=30';

function statistics(over: Partial<JevStatisticsResponse> = {}): JevStatisticsResponse {
  return { days: 30, since: '2026-10-10', usages: [], ...over };
}

/** The section reads its settings AND its statistics: each endpoint answers its own. */
function serveReads(current: JevSettings, stats: JevStatisticsResponse = statistics()) {
  return vi.spyOn(apiClient, 'get').mockImplementation(async requested => {
    if (requested === endpoint) return current;
    if (requested === statisticsEndpoint) return stats;
    throw new Error(`Unexpected request: ${requested}`);
  });
}
const sliderName = 'settings.admin.jev.thresholds.sliderLabel';
function emailUsage(value = 0.8): JevUsageStatus {
  return {
    usage: 'email_classification',
    label_key: 'settings.admin.jev.usages.email_classification',
    llm_type: 'jev_email_classification',
    enabled: true,
    effective: true,
    readiness: 'ready',
    qualified: value === 0.8,
    gates: [
      {
        key: 'priority',
        kind: 'choice_concentration',
        scope: 'each',
        default: 0.8,
        minimum: 0.5,
        maximum: 1,
        value,
      },
    ],
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('Jev administration', () => {
  it.each(['memory_reference_presence', 'hitl_rejection', 'parameter_kind'] as const)(
    'shows %s off while preserving existing preferences and toggles it alone',
    async usage => {
      const memoryLabel = `settings.admin.jev.usages.${usage}`;
      const initial = settings({ enabled: true });
      initial.usages.push({
        usage,
        label_key: memoryLabel,
        llm_type: `jev_${usage}`,
        enabled: false,
        effective: false,
        readiness: 'ready',
        gates: [],
        qualified: true,
      });
      const saved = structuredClone(initial);
      saved.usages[1].enabled = true;
      saved.usages[1].effective = true;
      serveReads(initial);
      const save = vi.spyOn(apiClient, 'patch').mockResolvedValue(saved);
      const { user } = renderWithProviders(<AdminJevSection lng="en" />);
      const control = await screen.findByRole('switch', { name: memoryLabel });
      expect(control).not.toBeChecked();
      expect(screen.getByRole('switch', { name: localLabel })).toBeChecked();
      expect(screen.getByRole('switch', { name: globalLabel })).toBeChecked();
      await user.click(control);
      await waitFor(() => expect(control).toBeChecked());
      expect(save).toHaveBeenCalledWith(endpoint, { usage, enabled: true }, undefined);
      expect(screen.getByRole('switch', { name: localLabel })).toBeChecked();
    }
  );

  it('recovers from an initial failed read without guessing a switch state', async () => {
    let offline = true;
    const get = vi.spyOn(apiClient, 'get').mockImplementation(async requested => {
      if (requested === statisticsEndpoint) return statistics();
      if (offline) {
        offline = false;
        throw new Error('offline');
      }
      return settings();
    });
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.admin.jev.loadError');
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'settings.admin.jev.refresh' }));
    expect(await screen.findByRole('switch', { name: localLabel })).toBeChecked();
    expect(get.mock.calls.filter(([requested]) => requested === endpoint)).toHaveLength(2);
  });
  it('does not claim OFF while the first read is pending', () => {
    vi.spyOn(apiClient, 'get').mockReturnValue(new Promise(() => {}));
    renderWithProviders(<AdminJevSection lng="en" />);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('common.loading');
  });

  it('keeps a local preference visible when the global circuit is off', async () => {
    serveReads(settings());
    renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByRole('switch', { name: localLabel })).toBeChecked();
    expect(screen.getByRole('switch', { name: globalLabel })).not.toBeChecked();
    expect(screen.getByText('settings.admin.jev.existing')).toBeInTheDocument();
  });

  it('writes only the selected switch and renders the server response', async () => {
    serveReads(settings());
    const response = settings();
    response.usages[0].enabled = false;
    const save = vi.spyOn(apiClient, 'patch').mockResolvedValue(response);
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: localLabel });
    await user.click(control);
    await waitFor(() => expect(control).not.toBeChecked());
    expect(save).toHaveBeenCalledWith(
      endpoint,
      { usage: 'meeting_template', enabled: false },
      undefined
    );
    expect(control).toHaveFocus();
  });

  it('keeps the previous state and focus after a rejected save', async () => {
    serveReads(settings());
    vi.spyOn(apiClient, 'patch').mockRejectedValue(new Error('unavailable'));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: localLabel });
    await user.click(control);
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.admin.jev.saveError');
    expect(control).toBeChecked();
    expect(control).toHaveFocus();
  });

  it('suppresses duplicate toggles while a save is pending', async () => {
    serveReads(settings());
    const save = vi.spyOn(apiClient, 'patch').mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: globalLabel });
    await user.click(control);
    await user.click(control);
    expect(save).toHaveBeenCalledTimes(1);
    expect(control).toHaveAttribute('aria-disabled', 'true');
    expect(control).toHaveFocus();
  });

  it('publishes each gate with the bounds the server declares and a translated name', async () => {
    serveReads(settings({ usages: [emailUsage()] }));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText('settings.admin.jev.thresholds.toggle'));
    const slider = await screen.findByRole('slider', { name: sliderName });
    expect(slider).toHaveAttribute('aria-valuemin', '0.5');
    expect(slider).toHaveAttribute('aria-valuemax', '1');
    expect(slider).toHaveAttribute('aria-valuenow', '0.8');
    expect(
      screen.getByText('settings.admin.jev.gates.email_classification.priority')
    ).toBeVisible();
    expect(
      screen.queryByText('settings.admin.jev.thresholds.outsideRecord')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'settings.admin.jev.thresholds.reset' })
    ).not.toBeInTheDocument();
  });

  it('commits one step of the keyboard as the gate value, at the hundredth', async () => {
    serveReads(settings({ usages: [emailUsage()] }));
    const save = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValue(settings({ usages: [emailUsage(0.81)] }));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText('settings.admin.jev.thresholds.toggle'));
    const slider = await screen.findByRole('slider', { name: sliderName });
    slider.focus();
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        thresholdsEndpoint,
        { usage: 'email_classification', values: { priority: 0.81 } },
        undefined
      )
    );
    await waitFor(() => expect(slider).toHaveAttribute('aria-valuenow', '0.81'));
    expect(await screen.findByText('settings.admin.jev.thresholds.outsideRecord')).toBeVisible();
  });

  it('names a usage outside its qualified record and puts its default back in one click', async () => {
    serveReads(settings({ usages: [emailUsage(0.6)] }));
    const save = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValue(settings({ usages: [emailUsage()] }));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByText('settings.admin.jev.thresholds.outsideRecord')).toBeVisible();
    await user.click(screen.getByText('settings.admin.jev.thresholds.toggle'));
    await user.click(screen.getByRole('button', { name: 'settings.admin.jev.thresholds.reset' }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        thresholdsEndpoint,
        { usage: 'email_classification', values: { priority: 0.8 } },
        undefined
      )
    );
    await waitFor(() =>
      expect(
        screen.queryByText('settings.admin.jev.thresholds.outsideRecord')
      ).not.toBeInTheDocument()
    );
    // The button left with the default it restored; the focus did not fall to the page.
    expect(
      screen.queryByRole('button', { name: 'settings.admin.jev.thresholds.reset' })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('slider', { name: sliderName })).toHaveFocus();
    expect(screen.getByRole('slider', { name: sliderName })).toHaveAttribute(
      'aria-valuenow',
      '0.8'
    );
  });

  it('names each gate as a group, so two resets of one usage stay distinct', async () => {
    const usage = emailUsage(0.6);
    usage.gates.push({ ...usage.gates[0], key: 'category', value: 0.7 });
    serveReads(settings({ usages: [usage] }));
    const save = vi.spyOn(apiClient, 'patch').mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText('settings.admin.jev.thresholds.toggle'));
    const category = screen.getByRole('group', {
      name: 'settings.admin.jev.gates.email_classification.category',
    });
    expect(within(category).getByRole('slider', { name: sliderName })).toHaveAttribute(
      'aria-valuenow',
      '0.7'
    );
    await user.click(
      within(category).getByRole('button', { name: 'settings.admin.jev.thresholds.reset' })
    );
    expect(save).toHaveBeenCalledWith(
      thresholdsEndpoint,
      { usage: 'email_classification', values: { category: 0.8 } },
      undefined
    );
  });

  it('keeps the stored value and says so when a threshold save fails', async () => {
    serveReads(settings({ usages: [emailUsage()] }));
    vi.spyOn(apiClient, 'patch').mockRejectedValue(new Error('unavailable'));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText('settings.admin.jev.thresholds.toggle'));
    const slider = await screen.findByRole('slider', { name: sliderName });
    slider.focus();
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.admin.jev.saveError');
    await waitFor(() => expect(slider).toHaveAttribute('aria-valuenow', '0.8'));
  });

  it('allows switching OFF even when configuration became unavailable', async () => {
    const initial = settings({ enabled: true });
    initial.usages[0].readiness = 'missing_key';
    serveReads(initial);
    const save = vi.spyOn(apiClient, 'patch').mockResolvedValue(settings());
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByRole('switch', { name: globalLabel }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(endpoint, { usage: null, enabled: false }, undefined)
    );
  });
});
