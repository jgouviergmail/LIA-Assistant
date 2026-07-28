/**
 * Mini-UI primitives of the /more scenes — presentational contract:
 * theme tokens only, no state, and, critically, NO interactive semantics
 * (stages are aria-hidden decoration; a button role inside would create an
 * unreachable focus stop for assistive tech).
 */

import { render, screen } from '@testing-library/react';
import { Bell } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import {
  Cursor,
  KeyCap,
  MiniBubble,
  MiniChip,
  MiniComposer,
  MiniGauge,
  MiniSettingRow,
  MiniToast,
  PhoneFrame,
  SkeletonLine,
} from '../primitives';

describe('primitives', () => {
  it('renders every primitive without any interactive role', () => {
    render(
      <div>
        <SkeletonLine w="w-16" />
        <MiniComposer trailing={<span>t</span>}>text</MiniComposer>
        <MiniBubble side="assistant">hello</MiniBubble>
        <MiniToast icon={Bell} tone="warning">
          warn
        </MiniToast>
        <MiniSettingRow icon={Bell} label="Theme" />
        <MiniChip>chip</MiniChip>
        <MiniGauge pct={40} />
        <KeyCap>/</KeyCap>
        <Cursor />
        <PhoneFrame>inside</PhoneFrame>
      </div>
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByText('inside')).toBeInTheDocument();
  });

  it('MiniGauge exposes its fill width as an inline style', () => {
    const { container } = render(<MiniGauge pct={78} />);
    const fill = container.querySelector('[data-fill]');
    expect(fill).toHaveStyle({ width: '78%' });
  });

  it('MiniBubble maps side and tone to alignment and border classes', () => {
    const { container: user } = render(<MiniBubble side="user">u</MiniBubble>);
    expect(user.firstElementChild?.className).toContain('self-end');

    const { container: err } = render(
      <MiniBubble side="assistant" tone="destructive">
        e
      </MiniBubble>
    );
    expect(err.firstElementChild?.className).toContain('border-destructive');
  });

  it('MiniToast renders its icon and tone styling', () => {
    const { container } = render(
      <MiniToast icon={Bell} tone="success">
        ok
      </MiniToast>
    );
    expect(container.querySelector('svg')).toBeInTheDocument();
    expect(screen.getByText('ok')).toBeInTheDocument();
  });

  it('KeyCap renders as a kbd element', () => {
    const { container } = render(<KeyCap>Tab</KeyCap>);
    expect(container.querySelector('kbd')).toHaveTextContent('Tab');
  });

  it('MiniSettingRow highlights on demand', () => {
    const { container } = render(<MiniSettingRow icon={Bell} label="Theme" highlighted />);
    expect(container.firstElementChild?.className).toContain('ring-');
  });
});
