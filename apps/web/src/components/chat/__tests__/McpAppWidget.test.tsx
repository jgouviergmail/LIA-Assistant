/**
 * McpAppWidget — widget airlock rendering tests (ADR-098).
 *
 * The widget must load the same-origin airlock shell (never srcDoc — that
 * would inherit the strict app CSP and re-break CDN-based widgets like
 * Excalidraw) and deliver the widget HTML via postMessage on iframe load.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

import { McpAppWidget } from '../McpAppWidget';
import { WIDGET_FRAME_PATH } from '@/lib/csp';
import type { McpAppRegistryPayload } from '@/types/mcp-apps';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The bridge wires window listeners + API calls — out of scope for these
// rendering tests (it is exercised end-to-end via the runtime validation).
vi.mock('@/hooks/useMcpAppBridge', () => ({
  useMcpAppBridge: vi.fn(),
}));

const PAYLOAD: McpAppRegistryPayload = {
  tool_name: 'create_view',
  server_name: 'Excalidraw',
  html_content: '<!doctype html><html><body>widget</body></html>',
  tool_result: '{}',
  server_id: '',
  server_key: 'excalidraw',
  server_source: 'admin',
  resource_uri: 'ui://excalidraw/view',
  tool_arguments: {},
};

vi.mock('@/lib/registry-context', () => ({
  useRegistryItem: (id: string) =>
    id === 'reg-1' ? { type: 'MCP_APP', payload: PAYLOAD } : undefined,
}));

describe('McpAppWidget (airlock rendering)', () => {
  it('renders an iframe pointing at the airlock shell, not srcDoc', () => {
    const { container } = render(<McpAppWidget registryId="reg-1" />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe!.getAttribute('src')).toBe(WIDGET_FRAME_PATH);
    expect(iframe!.hasAttribute('srcdoc')).toBe(false);
  });

  it('keeps the opaque-origin sandbox (no allow-same-origin)', () => {
    const { container } = render(<McpAppWidget registryId="reg-1" />);
    const sandbox = container.querySelector('iframe')!.getAttribute('sandbox')!;
    expect(sandbox).toContain('allow-scripts');
    expect(sandbox).not.toContain('allow-same-origin');
  });

  it('delivers the widget HTML to the shell via postMessage on iframe load', () => {
    const { container } = render(<McpAppWidget registryId="reg-1" />);
    const iframe = container.querySelector('iframe')!;
    const postMessage = vi.fn();
    // jsdom iframes have no real contentWindow navigation — stub it.
    Object.defineProperty(iframe, 'contentWindow', {
      value: { postMessage },
      configurable: true,
    });

    fireEvent.load(iframe);

    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(
      { type: 'lia:widget-html', html: PAYLOAD.html_content },
      '*'
    );
  });

  it('renders the unavailable placeholder when the registry item is missing', () => {
    const { container } = render(<McpAppWidget registryId="unknown" />);
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('.lia-mcp-app__placeholder')).not.toBeNull();
  });
});
