/**
 * The ephemeral scripts the ReAct loop ran, shown to administrators only.
 *
 * Owner arbitration (ADR-249): the code the model writes is visible in the
 * admin debug panel and NOWHERE else — not under the answer, not in the chat.
 * Hiding it entirely would buy no security (the model authored it, so it is
 * already in the context) and would cost all of the verifiability, which is the
 * reason to prefer a script over an LLM's mental arithmetic in the first place.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Accordion } from '@/components/ui/accordion';
import { ReactExecutionSection } from '../components/sections/ReactExecutionSection';
import type { ReactExecutionMetrics } from '@/types/chat';

function metrics(overrides: Partial<ReactExecutionMetrics> = {}): ReactExecutionMetrics {
  return {
    iterations: 3,
    max_iterations: 6,
    elapsed_seconds: 4.2,
    tool_names: ['search_emails_tool'],
    executed_tool_calls: 3,
    ...overrides,
  };
}

describe('ephemeral scripts in the ReAct debug section', () => {
  it('shows the code and its purpose when a script ran', () => {
    render(
      <Accordion type="multiple" defaultValue={['react_execution']}>
      <ReactExecutionSection
        data={metrics({
          scripts: [
            {
              purpose: 'sum the layover durations',
              code: 'import json,sys\nprint(sum(x["m"] for x in json.load(sys.stdin)["items"].values()))',
              success: true,
              output_head: '220',
            },
          ],
        })}
      />
      </Accordion>
    );

    expect(screen.getByText(/sum the layover durations/)).toBeInTheDocument();
    expect(screen.getByText(/json.load\(sys.stdin\)/)).toBeInTheDocument();
    expect(screen.getByText(/220/)).toBeInTheDocument();
  });

  it('marks a failed script so the admin sees what the model had to repair', () => {
    render(
      <Accordion type="multiple" defaultValue={['react_execution']}>
      <ReactExecutionSection
        data={metrics({
          scripts: [
            {
              purpose: 'divide',
              code: 'print(1/0)',
              success: false,
              output_head: 'ZeroDivisionError: division by zero',
            },
          ],
        })}
      />
      </Accordion>
    );

    expect(screen.getByText(/ZeroDivisionError/)).toBeInTheDocument();
  });

  it('renders nothing extra when no script ran', () => {
    render(
      <Accordion type="multiple" defaultValue={['react_execution']}>
        <ReactExecutionSection data={metrics()} />
      </Accordion>
    );

    expect(screen.queryByText(/Sandboxed scripts/i)).not.toBeInTheDocument();
  });
});
