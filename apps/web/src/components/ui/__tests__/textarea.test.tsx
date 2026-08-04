/**
 * Textarea — same accessible-name and error contract as `Input`.
 *
 * The two primitives share a contract, so they share a spec: whatever `Input`
 * promises about naming, identity and error reporting, `Textarea` promises too.
 * See `input.test.tsx` for why each clause exists.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Textarea } from '../textarea';

describe('Textarea — accessible name', () => {
  it('names the field from the label prop', () => {
    renderWithProviders(<Textarea label="Comment" />);
    expect(screen.getByRole('textbox', { name: 'Comment' })).toBeInTheDocument();
  });

  it('gives two fields sharing a label distinct ids', () => {
    renderWithProviders(
      <>
        <Textarea label="Notes" />
        <Textarea label="Notes" />
      </>
    );
    const [first, second] = screen.getAllByRole('textbox', { name: 'Notes' });
    expect(first.id).not.toBe('');
    expect(first.id).not.toBe(second.id);
  });

  it('honours an explicit id over the generated one', () => {
    renderWithProviders(<Textarea id="chosen-id" label="Comment" />);
    expect(screen.getByRole('textbox', { name: 'Comment' })).toHaveAttribute('id', 'chosen-id');
  });

  it('still emits an id when neither label nor id is given', () => {
    renderWithProviders(<Textarea aria-label="Bare" />);
    expect(screen.getByRole('textbox', { name: 'Bare' }).id).not.toBe('');
  });
});

describe('Textarea — error contract', () => {
  it('marks the field invalid and describes it with the message', () => {
    renderWithProviders(<Textarea label="Comment" error="Too short" />);
    const field = screen.getByRole('textbox', { name: 'Comment' });
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription('Too short');
  });

  it('announces the message as an alert', () => {
    renderWithProviders(<Textarea label="Comment" error="Too short" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Too short');
  });

  it('leaves a valid field unmarked and undescribed', () => {
    renderWithProviders(<Textarea label="Comment" />);
    const field = screen.getByRole('textbox', { name: 'Comment' });
    expect(field).not.toHaveAttribute('aria-invalid');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('treats an empty error string as no error', () => {
    renderWithProviders(<Textarea label="Comment" error="" />);
    expect(screen.getByRole('textbox', { name: 'Comment' })).not.toHaveAttribute('aria-invalid');
  });

  it('keeps a caller-supplied description and adds the error to it', () => {
    renderWithProviders(
      <>
        <span id="rules">Max 500 characters</span>
        <Textarea label="Comment" aria-describedby="rules" error="Too short" />
      </>
    );
    expect(screen.getByRole('textbox', { name: 'Comment' })).toHaveAccessibleDescription(
      'Max 500 characters Too short'
    );
  });
});
