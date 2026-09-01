/**
 * ToolDisplayName — one rule, two screens.
 *
 * The user MCP list and the admin MCP list show the same thing: a tool as the
 * server named it. Raw MCP names are machine identifiers, so the spec's
 * `title` leads when there is one; the identifier stays beside it because that
 * is the string that appears in logs and in the call the model makes. Keeping
 * that rule in one place is what stops the two screens from drifting apart —
 * which the two copies of the list markup had already done.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { ToolDisplayName } from '../ToolDisplayName';

describe('ToolDisplayName', () => {
  it('leads with the declared title', () => {
    renderWithProviders(<ToolDisplayName title="Financial accounts" name="accounts__list" />);
    expect(screen.getByText('Financial accounts')).toBeInTheDocument();
  });

  it('keeps the identifier visible beside the title', () => {
    renderWithProviders(<ToolDisplayName title="Financial accounts" name="accounts__list" />);
    expect(screen.getByText('accounts__list')).toBeInTheDocument();
  });

  it('shows the identifier alone when no title is declared', () => {
    renderWithProviders(<ToolDisplayName name="accounts__list" />);
    expect(screen.getByText('accounts__list')).toBeInTheDocument();
  });

  it('does not render the identifier twice when there is no title', () => {
    renderWithProviders(<ToolDisplayName name="accounts__list" />);
    expect(screen.getAllByText('accounts__list')).toHaveLength(1);
  });

  it('treats a blank title as no title', () => {
    renderWithProviders(<ToolDisplayName title="   " name="accounts__list" />);
    expect(screen.getAllByText('accounts__list')).toHaveLength(1);
  });

  it('treats a null title as no title', () => {
    renderWithProviders(<ToolDisplayName title={null} name="accounts__list" />);
    expect(screen.getAllByText('accounts__list')).toHaveLength(1);
  });
});
