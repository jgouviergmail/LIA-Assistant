/**
 * DisconnectConnectorConfirm (W4a) — in-app confirmation that names the target.
 *
 * The native `confirm` it replaces asked "disconnect this service?" from a page
 * listing several connected services: nothing told the user WHICH card had been
 * clicked, and the OK/Cancel buttons came from the operating system, in the
 * OS language rather than the app's.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { DisconnectConnectorConfirm } from '../DisconnectConnectorConfirm';

const onConfirm = vi.fn();
const onOpenChange = vi.fn();

function renderDialog(open = true, connectorLabel = 'Gmail') {
  return render(
    <DisconnectConnectorConfirm
      open={open}
      onOpenChange={onOpenChange}
      connectorLabel={connectorLabel}
      onConfirm={onConfirm}
    />
  );
}

beforeEach(() => {
  onConfirm.mockReset();
  onOpenChange.mockReset();
});

describe('DisconnectConnectorConfirm', () => {
  it('renders nothing while closed', () => {
    renderDialog(false);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('announces itself as an alert dialog', () => {
    renderDialog();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('names the connector in both the title and the body', () => {
    // The i18n stub echoes keys, so the interpolation itself is not visible
    // here; what matters is that BOTH slots are wired to the named keys rather
    // than to a generic "this service" string.
    renderDialog();
    expect(screen.getByText('settings.connectors.disconnect_title')).toBeInTheDocument();
    expect(screen.getByText('settings.connectors.disconnect_description')).toBeInTheDocument();
  });

  it('confirms once', () => {
    renderDialog();
    fireEvent.click(screen.getByText('settings.connectors.disconnect'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('offers a cancel that does NOT confirm', () => {
    renderDialog();
    fireEvent.click(screen.getByText('common.cancel'));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
