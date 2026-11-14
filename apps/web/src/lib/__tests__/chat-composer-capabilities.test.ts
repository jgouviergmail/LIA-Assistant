/**
 * The composer offers what the instance offers NOW.
 *
 * The meeting recorder, the meeting import and the knowledge-space documents
 * read the deployment ceiling alone: an operator who had switched the meetings
 * or the spaces off still saw their entries in the « + », and every click was
 * refused.
 */
import { describe, expect, it } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { composerFeatureFlags } from '@/lib/chat-composer-capabilities';

const OFFERED = appConfigFixture({
  features: { meetings_enabled: true, meetings_import_enabled: true, rag_spaces_enabled: true },
});

describe('composerFeatureFlags', () => {
  it('offers the meetings and the knowledge documents where the deployment mounts them', () => {
    expect(composerFeatureFlags(OFFERED)).toMatchObject({
      meetingsEnabled: true,
      meetingImportEnabled: true,
      knowledgeDocumentsEnabled: true,
    });
  });

  it('withdraws the recorder and the import once the operator switched the meetings off', () => {
    const flags = composerFeatureFlags({
      ...OFFERED,
      capabilities: { meetings: { enabled: false, family: 'media' } },
    });

    expect(flags.meetingsEnabled).toBe(false);
    expect(flags.meetingImportEnabled).toBe(false);
    // Another capability's entry is not this switch's business.
    expect(flags.knowledgeDocumentsEnabled).toBe(true);
  });

  it('withdraws the knowledge documents once the operator switched the spaces off', () => {
    const flags = composerFeatureFlags({
      ...OFFERED,
      capabilities: { rag_spaces: { enabled: false, family: 'knowledge' } },
    });

    expect(flags.knowledgeDocumentsEnabled).toBe(false);
    expect(flags.meetingsEnabled).toBe(true);
    expect(flags.meetingImportEnabled).toBe(true);
  });

  it('withdraws the upload once the operator switched the attachments off', () => {
    const flags = composerFeatureFlags({
      ...OFFERED,
      capabilities: { attachments: { enabled: false, family: 'media' } },
    });

    expect(flags.attachmentsEnabled).toBe(false);
    // A file LIA produced is the person's to bring back whatever the switch says.
    expect(flags.generatedFilesEnabled).toBe(true);
  });

  it('keeps its defaults before the configuration answers', () => {
    expect(composerFeatureFlags(null)).toEqual({
      attachmentsEnabled: true,
      // What an older API takes: the historical images and PDFs.
      attachmentFormats: { image_types: [], document_extensions: ['.pdf'] },
      knowledgeDocumentsEnabled: false,
      bookmarksEnabled: false,
      generatedFilesEnabled: true,
      meetingImportEnabled: false,
      meetingsEnabled: false,
    });
  });
});

describe('composerFeatureFlags — while LIA answers (ADR-384)', () => {
  it('offers no attachment source: only words can wait their turn', () => {
    const flags = composerFeatureFlags(OFFERED, { textOnly: true });
    expect(flags).toMatchObject({
      attachmentsEnabled: false,
      knowledgeDocumentsEnabled: false,
      bookmarksEnabled: false,
      generatedFilesEnabled: false,
    });
    // The recorder is not a part of a message: a recording goes on.
    expect(flags.meetingsEnabled).toBe(composerFeatureFlags(OFFERED).meetingsEnabled);
  });
});

describe('composerFeatureFlags — what an upload takes', () => {
  it('hands the composer the formats the instance publishes', () => {
    const published = { image_types: ['image/png'], document_extensions: ['.docx', '.pdf'] };

    expect(composerFeatureFlags(appConfigFixture({ attachments: published }))).toMatchObject({
      attachmentFormats: published,
    });
  });
});
