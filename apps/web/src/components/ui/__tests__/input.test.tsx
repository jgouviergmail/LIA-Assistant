/**
 * Input — accessible name, unique identity and the programmatic error contract.
 *
 * The error state used to be purely visual (a red border and a red paragraph),
 * so a screen-reader user tabbing into an invalid field heard the label and
 * nothing else: neither that the field was rejected, nor why. WCAG 3.3.1 (Error
 * Identification) and 1.3.1 (Info and Relationships) are both level A, so the
 * contract is asserted here rather than left to a visual review.
 *
 * Identity matters just as much: the id used to be derived from the label text,
 * so two fields sharing a label (common in settings) collided on one id and the
 * second label pointed at the first field — and the id changed with the active
 * locale.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Input } from '../input';

describe('Input — accessible name', () => {
  it('names the field from the label prop', () => {
    renderWithProviders(<Input label="Email" />);
    expect(screen.getByRole('textbox', { name: 'Email' })).toBeInTheDocument();
  });

  it('gives two fields sharing a label distinct ids', () => {
    renderWithProviders(
      <>
        <Input label="Name" />
        <Input label="Name" />
      </>
    );
    const [first, second] = screen.getAllByRole('textbox', { name: 'Name' });
    expect(first.id).not.toBe('');
    expect(first.id).not.toBe(second.id);
  });

  it('honours an explicit id over the generated one', () => {
    renderWithProviders(<Input id="chosen-id" label="Email" />);
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAttribute('id', 'chosen-id');
  });

  it('still emits an id when neither label nor id is given', () => {
    // Without an id the field cannot be targeted by an external
    // `<Label htmlFor>` — the pattern used across the settings screens.
    renderWithProviders(<Input aria-label="Bare" />);
    expect(screen.getByRole('textbox', { name: 'Bare' }).id).not.toBe('');
  });
});

describe('Input — error contract', () => {
  it('marks the field invalid and describes it with the message', () => {
    renderWithProviders(<Input label="Email" error="Invalid address" />);
    const field = screen.getByRole('textbox', { name: 'Email' });
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription('Invalid address');
  });

  it('announces the message as an alert', () => {
    renderWithProviders(<Input label="Email" error="Invalid address" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid address');
  });

  it('leaves a valid field unmarked and undescribed', () => {
    renderWithProviders(<Input label="Email" />);
    const field = screen.getByRole('textbox', { name: 'Email' });
    expect(field).not.toHaveAttribute('aria-invalid');
    expect(field).toHaveAccessibleDescription('');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('treats an empty error string as no error', () => {
    renderWithProviders(<Input label="Email" error="" />);
    expect(screen.getByRole('textbox', { name: 'Email' })).not.toHaveAttribute('aria-invalid');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps a caller-supplied description and adds the error to it', () => {
    // A field that already documents its format must not lose that hint the
    // moment it is rejected — the two descriptions are additive.
    renderWithProviders(
      <>
        <span id="hint">Must contain an @</span>
        <Input label="Email" aria-describedby="hint" error="Invalid address" />
      </>
    );
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAccessibleDescription(
      'Must contain an @ Invalid address'
    );
  });

  it('keeps a caller-supplied description when there is no error', () => {
    renderWithProviders(
      <>
        <span id="hint">Must contain an @</span>
        <Input label="Email" aria-describedby="hint" />
      </>
    );
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAccessibleDescription(
      'Must contain an @'
    );
  });
});
