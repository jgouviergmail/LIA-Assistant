/**
 * The six NEW stage sections (v3.4): semantic validator, ReAct loop, image
 * generation, HITL, voice and compaction — the stages the panel could not
 * see before.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Accordion } from '@/components/ui/accordion';
import { SemanticValidatorSection } from '../SemanticValidatorSection';
import { ReactExecutionSection } from '../ReactExecutionSection';
import { ImageGenerationSection } from '../ImageGenerationSection';
import { HitlSection } from '../HitlSection';
import { VoiceSection } from '../VoiceSection';
import { CompactionSection } from '../CompactionSection';

function open(values: string[], ui: React.ReactNode) {
  return render(
    <Accordion type="multiple" defaultValue={values}>
      {ui}
    </Accordion>
  );
}

describe('SemanticValidatorSection', () => {
  it('renders a rejected verdict as INFORMATIVE, never as a blockage claim (ADR-184)', () => {
    open(
      ['semantic_validation'],
      <SemanticValidatorSection
        data={{
          is_valid: false,
          confidence: 0.55,
          criticality: 'MEDIUM',
          requires_clarification: false,
          clarification_questions: [],
          validation_duration_seconds: 1.2,
          used_fallback: false,
          fallback_reason: null,
          issues: [
            {
              issue_type: 'scope_underflow',
              description: 'Plan ignores the date constraint',
              severity: 'high',
              step_index: 1,
              suggested_fix: 'Add the date filter',
            },
          ],
        }}
      />
    );
    expect(screen.getByText('Semantic Validator')).toBeInTheDocument();
    expect(screen.getByText('scope_underflow')).toBeInTheDocument();
    expect(screen.getByText('Plan ignores the date constraint')).toBeInTheDocument();
    // The ADR-184 doctrine is stated in place: the verdict does not block.
    expect(screen.getByText(/informative/i)).toBeInTheDocument();
  });

  it('renders a neutral empty state when the validator did not run', () => {
    open(['semantic_validation'], <SemanticValidatorSection data={undefined} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });
});

describe('ReactExecutionSection', () => {
  it('shows iterations against the PUBLISHED bound with the tool roster', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{
          iterations: 3,
          max_iterations: 10,
          elapsed_seconds: 12.5,
          tool_names: ['get_emails_tool', 'get_events_tool'],
          executed_tool_calls: 2,
        }}
      />
    );
    expect(screen.getByText('ReAct Loop')).toBeInTheDocument();
    expect(screen.getAllByText('3/10').length).toBeGreaterThan(0);
    expect(screen.getByText('get_emails_tool')).toBeInTheDocument();
  });

  it('warns when the loop hit its iteration ceiling', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{
          iterations: 10,
          max_iterations: 10,
          elapsed_seconds: 60,
          tool_names: [],
          executed_tool_calls: 9,
        }}
      />
    );
    expect(screen.getByText(/ceiling/i)).toBeInTheDocument();
  });
});

describe('ImageGenerationSection', () => {
  it('shows the aggregate and per-call details', () => {
    open(
      ['image_generation'],
      <ImageGenerationSection
        calls={[
          {
            model: 'gpt-image-1',
            quality: 'medium',
            size: '1024x1024',
            image_count: 2,
            cost_usd: 0.08,
            cost_eur: 0.074,
            duration_ms: 9000,
            prompt_preview: 'a lighthouse at dawn',
          },
        ]}
        summary={{ total_calls: 1, total_images: 2, total_cost_usd: 0.08, total_cost_eur: 0.074 }}
      />
    );
    expect(screen.getByText('Image Generation')).toBeInTheDocument();
    expect(screen.getByText('gpt-image-1')).toBeInTheDocument();
    expect(screen.getByText(/a lighthouse at dawn/)).toBeInTheDocument();
    expect(screen.getAllByText('2 images').length).toBeGreaterThan(0);
  });
});

describe('HitlSection', () => {
  it('shows an interrupted run waiting on the user', () => {
    open(
      ['hitl'],
      <HitlSection
        data={{
          interrupted: true,
          interrupt_action_type: 'draft_critique',
          interrupt_tool_name: 'send_email_tool',
          plan_approved: false,
          clarification_response: null,
          clarification_field: null,
          for_each_cancelled: false,
          cancellation_reason: null,
        }}
      />
    );
    expect(screen.getByText('Human in the Loop')).toBeInTheDocument();
    expect(screen.getByText('draft_critique')).toBeInTheDocument();
    expect(screen.getByText(/waiting/i)).toBeInTheDocument();
  });

  it('shows a resumed run with the user decision', () => {
    open(
      ['hitl'],
      <HitlSection
        data={{
          interrupted: false,
          interrupt_action_type: null,
          interrupt_tool_name: null,
          plan_approved: true,
          clarification_response: 'oui, envoie',
          clarification_field: 'subject',
          for_each_cancelled: false,
          cancellation_reason: null,
        }}
      />
    );
    expect(screen.getByText(/oui, envoie/)).toBeInTheDocument();
  });
});

describe('VoiceSection', () => {
  it('shows the TTS spend per call', () => {
    open(
      ['voice'],
      <VoiceSection
        data={{
          total_calls: 1,
          total_characters: 420,
          total_cost_eur: 0.0058,
          calls: [
            { provider: 'openai', model: 'tts-1', characters: 420, cost_eur: 0.0058, duration_ms: 850 },
          ],
        }}
      />
    );
    expect(screen.getByText('Voice Synthesis')).toBeInTheDocument();
    expect(screen.getByText('tts-1')).toBeInTheDocument();
    expect(screen.getAllByText(/420/).length).toBeGreaterThan(0);
  });
});

describe('CompactionSection', () => {
  it('shows strategy, savings and the bounded summary preview', () => {
    open(
      ['compaction'],
      <CompactionSection
        data={{
          count: 2,
          strategy: 'llm_summary',
          tokens_saved: 1200,
          duration_ms: null,
          messages_removed: 14,
          summary_preview: 'Earlier the user asked about…',
        }}
      />
    );
    expect(screen.getByText('Context Compaction')).toBeInTheDocument();
    expect(screen.getByText('llm_summary')).toBeInTheDocument();
    expect(screen.getByText(/Earlier the user asked/)).toBeInTheDocument();
  });
});
