/**
 * How one generated file presents itself (ADR-279).
 *
 * The three questions a card asks — what to call it, where opening it leads,
 * and how urgently its deadline reads — are pure functions, so they are pinned
 * here rather than through a grid.
 */

import { describe, expect, it } from 'vitest';

import {
  EXPIRY_WARNING_HOURS,
  assetLabel,
  assetOpenHref,
  expiryTone,
} from '@/lib/generated-assets/display';
import type { GeneratedAsset } from '@/types/generated-assets';

function asset(over: Partial<GeneratedAsset> = {}): GeneratedAsset {
  return {
    id: 'a1b2c3d4-0000-4000-8000-000000000001',
    title: null,
    original_filename: 'rapport.pdf',
    mime_type: 'application/pdf',
    file_size: 1024,
    origin: 'generated_document',
    conversation_id: null,
    created_at: '2026-09-10T08:00:00Z',
    expires_at: '2026-09-11T08:00:00Z',
    ...over,
  };
}

describe('assetLabel', () => {
  it('prefers the title its producer gave it', () => {
    expect(assetLabel(asset({ title: 'Bilan du trimestre' }))).toBe('Bilan du trimestre');
  });

  it('falls back to the download filename', () => {
    expect(assetLabel(asset({ title: null }))).toBe('rapport.pdf');
  });

  it('treats a blank title as no title, never as a nameless card', () => {
    expect(assetLabel(asset({ title: '   ' }))).toBe('rapport.pdf');
  });
});

describe('assetOpenHref', () => {
  it('opens a PDF in the browser’s own viewer', () => {
    // The SAME rule the chat card follows: two rules would eventually send the
    // same file to two places.
    expect(assetOpenHref(asset({ mime_type: 'application/pdf' }), 'fr')).toContain(
      '/api/v1/attachments/'
    );
  });

  it('opens an image inline too', () => {
    expect(assetOpenHref(asset({ mime_type: 'image/png' }), 'fr')).toContain(
      '/api/v1/attachments/'
    );
  });

  it('sends every other type to the document viewer, with its name', () => {
    const href = assetOpenHref(
      asset({ mime_type: 'text/csv', original_filename: 'modeles.csv' }),
      'fr'
    );
    expect(href).toContain('/fr/dashboard/documents/');
    expect(href).toContain('name=modeles.csv');
    expect(href).toContain('type=csv');
  });

  it('never builds a viewer link without the language', () => {
    expect(assetOpenHref(asset({ mime_type: 'text/csv' }), 'zh')).toContain('/zh/dashboard/');
  });
});

describe('expiryTone', () => {
  const now = Date.parse('2026-09-10T08:00:00Z');

  it('is muted while the deadline is far off', () => {
    expect(expiryTone('2026-09-11T08:00:00Z', now)).toBe('text-muted-foreground');
  });

  it('warns once the deadline is close', () => {
    const soon = new Date(now + (EXPIRY_WARNING_HOURS - 1) * 3600 * 1000).toISOString();
    expect(expiryTone(soon, now)).toContain('amber');
  });

  it('is destructive once the deadline has passed', () => {
    expect(expiryTone('2026-09-10T07:59:00Z', now)).toBe('text-destructive');
  });

  it('reads an unparsable deadline as gone rather than as fine', () => {
    // Saying « plenty of time » about a date nobody could read is the wrong
    // way to be wrong: the person would not save the file.
    expect(expiryTone('not-a-date', now)).toBe('text-destructive');
  });
});
