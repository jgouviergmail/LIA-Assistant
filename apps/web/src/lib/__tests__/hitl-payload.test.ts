/**
 * hitl-payload normalizer — fixtures are the REAL wire payloads captured at
 * runtime during Lot 1 Phase 0 (scratchpad/t03-captures), not hand-written
 * approximations. The normalizer is the single entry for both sources:
 * `hitl_interrupt_metadata` SSE chunk metadata and the
 * GET /agents/hitl/pending body (same de-facto shape).
 *
 * V1 line: cards for draft_critique / tool_confirmation /
 * destructive_confirm / for_each_confirmation; clarification and anything
 * unknown return null (text-only flow, never a crash).
 */

import { describe, it, expect } from 'vitest';

import { normalizeHitlPayload } from '@/lib/hitl-payload';

// --- REAL capture: draft_critique (user account, pipeline, 2026-07-18) ----
const DRAFT_METADATA = {
  message_id: 'hitl_35e9301b-86e1-4665-b47a-23363fff33aa_3acd0828f617ad75b7f2a36f2dd1f67f',
  conversation_id: '35e9301b-86e1-4665-b47a-23363fff33aa',
  action_requests: [
    {
      type: 'draft_critique',
      draft_type: 'email',
      draft_id: 'draft_8b8eb7fc2cf7',
      draft_content: {
        related_registry_ids: [],
        user_language: 'fr',
        user_timezone: 'Europe/Paris',
        to: 'user@example.com',
        subject: '[TEST LIA] Brouillon de test — à ignorer',
        body: 'Ceci est un brouillon de test technique, il ne sera pas envoyé.',
        cc: null,
        bcc: null,
        is_html: false,
      },
      available_actions: [
        { action: 'confirm', label: 'confirm', style: 'primary' },
        { action: 'edit', label: 'edit', style: 'secondary' },
        { action: 'cancel', label: 'cancel', style: 'destructive' },
      ],
      registry_ids: ['draft_8b8eb7fc2cf7'],
    },
  ],
  count: 1,
  is_plan_approval: false,
  draft_type: 'email',
  draft_id: 'draft_8b8eb7fc2cf7',
  available_actions: ['confirm', 'edit', 'cancel'],
  registry_ids: ['draft_8b8eb7fc2cf7'],
  has_registry_items: true,
};

// --- REAL capture: tool_confirmation (ReAct sub-agent delegation) ---------
// Captured BEFORE T1.1: no available_actions on the wire — the normalizer
// must fall back to the canonical confirm/cancel pair.
const TOOL_METADATA_LEGACY = {
  message_id: 'hitl_5ad8137a-bd6b-4a3d-a4ff-60e1acdd7f39_3ad0512ddafb25127af36712fb29219d',
  conversation_id: '5ad8137a-bd6b-4a3d-a4ff-60e1acdd7f39',
  action_requests: [
    {
      type: 'tool_confirmation',
      tool_name: 'delegate_to_sub_agent_tool',
      tool_args: {
        expertise: 'poète spécialiste des haïkus',
        instruction: 'Rédige un court haïku…',
      },
      registry_ids: [],
    },
  ],
  count: 1,
  is_plan_approval: false,
  tool_name: 'delegate_to_sub_agent_tool',
  registry_ids: [],
  has_registry_items: false,
};

// --- Code-contract emission: destructive_confirm (destructive_confirm.py) -
const DESTRUCTIVE_METADATA = {
  message_id: 'hitl_conv_destructive',
  conversation_id: 'conv-1',
  action_requests: [
    {
      type: 'destructive_confirm',
      operation_type: 'delete_emails',
      affected_count: 15,
      available_actions: [
        { action: 'confirm_delete', label: 'confirm_deletion', style: 'destructive' },
        { action: 'cancel', label: 'keep_items', style: 'secondary' },
      ],
      registry_ids: [],
    },
  ],
  count: 1,
  is_plan_approval: false,
  operation_type: 'delete_emails',
  affected_count: 15,
  severity: 'critical',
  registry_ids: [],
  has_registry_items: false,
};

// --- Code-contract emission: for_each_confirmation (for_each_confirmation.py)
const FOR_EACH_METADATA = {
  message_id: 'hitl_conv_foreach',
  conversation_id: 'conv-1',
  action_requests: [
    {
      type: 'for_each_confirmation',
      plan_id: 'plan_42',
      steps: [{ step_id: 'step_1' }],
      total_affected: 8,
      available_actions: [
        { action: 'confirm', label: 'Confirm', style: 'primary' },
        { action: 'cancel', label: 'Cancel', style: 'secondary' },
      ],
      registry_ids: [],
      item_previews: [{ name: 'Jean' }, { name: 'Marie' }],
    },
  ],
  count: 1,
  is_plan_approval: false,
  plan_id: 'plan_42',
  total_affected: 8,
  steps_count: 1,
  severity: 'warning',
  registry_ids: [],
  item_previews: [{ name: 'Jean' }, { name: 'Marie' }],
};

// --- REAL capture: clarification (semantic validator, admin account) ------
const CLARIFICATION_METADATA = {
  message_id: 'hitl_5ad8137a-bd6b-4a3d-a4ff-60e1acdd7f39_15a612cd862412dc10ecaf4ea5aa9499',
  conversation_id: '5ad8137a-bd6b-4a3d-a4ff-60e1acdd7f39',
  action_requests: [
    {
      type: 'clarification',
      clarification_questions: [
        "Fabricated placeholder contact detail: step_1.to='test@example.com'",
      ],
      semantic_issues: [
        {
          type: 'wrong_parameters',
          description: "Fabricated placeholder contact detail: step_1.to='test@example.com'",
          severity: 'high',
        },
      ],
      registry_ids: [],
    },
  ],
  count: 1,
  is_plan_approval: false,
  question_count: 1,
  issue_count: 1,
  issue_types: ['wrong_parameters'],
  registry_ids: [],
  has_registry_items: false,
};

describe('normalizeHitlPayload — draft_critique (real capture)', () => {
  it('maps identity, typed content and backend-driven actions', () => {
    const result = normalizeHitlPayload(DRAFT_METADATA);

    expect(result).not.toBeNull();
    expect(result?.kind).toBe('draft_critique');
    expect(result?.messageId).toBe(DRAFT_METADATA.message_id);
    expect(result?.draftId).toBe('draft_8b8eb7fc2cf7');
    expect(result?.draftType).toBe('email');
    expect(result?.draftContent).toMatchObject({
      to: 'user@example.com',
      subject: '[TEST LIA] Brouillon de test — à ignorer',
    });
    // P1-V2: the structured "edit" action is kept on draft cards — it opens
    // the inline instructions form (live modification loop, no classifier).
    expect(result?.actions.map(a => a.action)).toEqual(['confirm', 'edit', 'cancel']);
    expect(result?.actions.find(a => a.action === 'cancel')?.style).toBe('destructive');
    expect(result?.actions.find(a => a.action === 'edit')?.style).toBe('secondary');
  });

  it('edit stays filtered out on non-draft kinds (server rejects it there)', () => {
    const tool = structuredClone(TOOL_METADATA_LEGACY) as Record<string, unknown>;
    (tool.action_requests as Record<string, unknown>[])[0].available_actions = [
      { action: 'confirm', label: 'confirm', style: 'primary' },
      { action: 'edit', label: 'edit', style: 'secondary' },
      { action: 'cancel', label: 'cancel', style: 'destructive' },
    ];
    const result = normalizeHitlPayload(tool);
    expect(result?.actions.map(a => a.action)).toEqual(['confirm', 'cancel']);
  });

  it('returns null when draft_id is missing (unusable resume)', () => {
    const broken = structuredClone(DRAFT_METADATA) as Record<string, unknown>;
    delete (broken.action_requests as Record<string, unknown>[])[0].draft_id;
    delete broken.draft_id;
    expect(normalizeHitlPayload(broken)).toBeNull();
  });
});

describe('normalizeHitlPayload — tool_confirmation (real ReAct capture)', () => {
  it('maps tool identity and falls back to canonical actions pre-T1.1', () => {
    const result = normalizeHitlPayload(TOOL_METADATA_LEGACY);

    expect(result?.kind).toBe('tool_confirmation');
    expect(result?.toolName).toBe('delegate_to_sub_agent_tool');
    expect(result?.toolArgs).toMatchObject({ expertise: 'poète spécialiste des haïkus' });
    expect(result?.actions.map(a => a.action)).toEqual(['confirm', 'cancel']);
    expect(result?.actions.find(a => a.action === 'confirm')?.style).toBe('primary');
  });
});

describe('normalizeHitlPayload — destructive_confirm (code contract)', () => {
  it('keeps wire action ids verbatim (server canonicalizes aliases)', () => {
    const result = normalizeHitlPayload(DESTRUCTIVE_METADATA);

    expect(result?.kind).toBe('destructive_confirm');
    expect(result?.severity).toBe('critical');
    expect(result?.operationType).toBe('delete_emails');
    expect(result?.affectedCount).toBe(15);
    expect(result?.actions.map(a => a.action)).toEqual(['confirm_delete', 'cancel']);
  });
});

describe('normalizeHitlPayload — for_each_confirmation (code contract)', () => {
  it('maps scale display fields and previews', () => {
    const result = normalizeHitlPayload(FOR_EACH_METADATA);

    expect(result?.kind).toBe('for_each_confirmation');
    expect(result?.affectedCount).toBe(8);
    expect(result?.previewItems).toEqual([{ name: 'Jean' }, { name: 'Marie' }]);
    expect(result?.severity).toBe('warning');
    expect(result?.actions.map(a => a.action)).toEqual(['confirm', 'cancel']);
  });
});

describe('normalizeHitlPayload — out of V1 scope and defensive', () => {
  it('clarification returns null (text-only until P1-V3)', () => {
    expect(normalizeHitlPayload(CLARIFICATION_METADATA)).toBeNull();
  });

  it('unknown interrupt types return null, never crash', () => {
    expect(
      normalizeHitlPayload({
        message_id: 'x',
        action_requests: [{ type: 'entity_disambiguation' }],
      })
    ).toBeNull();
  });

  it('garbage inputs return null, never crash', () => {
    expect(normalizeHitlPayload(null)).toBeNull();
    expect(normalizeHitlPayload(undefined)).toBeNull();
    expect(normalizeHitlPayload('nope')).toBeNull();
    expect(normalizeHitlPayload({})).toBeNull();
    expect(normalizeHitlPayload({ action_requests: [] })).toBeNull();
    expect(normalizeHitlPayload({ action_requests: [null] })).toBeNull();
  });

  it('hydration body (GET /agents/hitl/pending) normalizes identically', () => {
    // Same de-facto shape + interrupt_ts — carried through for expiry display.
    const hydration = {
      ...structuredClone(TOOL_METADATA_LEGACY),
      interrupt_ts: '2026-07-18T19:00:00+00:00',
    };
    const result = normalizeHitlPayload(hydration);

    expect(result?.kind).toBe('tool_confirmation');
    expect(result?.interruptTs).toBe('2026-07-18T19:00:00+00:00');
  });
});
