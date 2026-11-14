/**
 * What the composer offers for an upload is what the server will take.
 *
 * The picker and the drop zone used to say « images and PDFs » in the page
 * itself. The server now publishes its own allowlists, and a document is
 * recognised by its NAME: a browser reports no type at all for a `.md`, and
 * `application/vnd.ms-excel` for a `.csv` on a desktop with a spreadsheet
 * installed.
 */
import { describe, expect, it } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import {
  DEFAULT_ATTACHMENT_FORMATS,
  acceptedFiles,
  attachmentFormats,
  pickerAccept,
} from '@/lib/attachment-formats';

const PUBLISHED = {
  image_types: ['image/jpeg', 'image/png'],
  document_extensions: ['.csv', '.docx', '.md', '.pdf'],
};

function file(name: string, type = ''): File {
  return new File(['x'], name, { type });
}

describe('attachmentFormats', () => {
  it('reads what the instance publishes', () => {
    expect(attachmentFormats(appConfigFixture({ attachments: PUBLISHED }))).toEqual(PUBLISHED);
  });

  it('keeps the historical images and PDFs for a server that publishes nothing', () => {
    expect(attachmentFormats(appConfigFixture())).toEqual(DEFAULT_ATTACHMENT_FORMATS);
    expect(attachmentFormats(null)).toEqual(DEFAULT_ATTACHMENT_FORMATS);
    expect(pickerAccept(DEFAULT_ATTACHMENT_FORMATS)).toBe('image/*,.pdf');
  });
});

describe('pickerAccept', () => {
  it('offers every image and the published document extensions', () => {
    expect(pickerAccept(PUBLISHED)).toBe('image/*,.csv,.docx,.md,.pdf');
  });

  it('offers images alone when the instance takes no document', () => {
    expect(pickerAccept({ image_types: ['image/png'], document_extensions: [] })).toBe('image/*');
  });
});

describe('acceptedFiles', () => {
  it('takes a picture by its type and a document by its name', () => {
    const dropped = [
      file('photo.heic', 'image/heic'),
      file('notes.md'),
      file('export.CSV', 'application/vnd.ms-excel'),
      file('report.docx', 'application/octet-stream'),
      file('contract.pdf', 'application/pdf'),
    ];

    expect(acceptedFiles(dropped, PUBLISHED).map(f => f.name)).toEqual([
      'photo.heic',
      'notes.md',
      'export.CSV',
      'report.docx',
      'contract.pdf',
    ]);
  });

  it('leaves out what the server would refuse', () => {
    const dropped = [file('archive.zip', 'application/zip'), file('song.mp3', 'audio/mpeg')];

    expect(acceptedFiles(dropped, PUBLISHED)).toEqual([]);
  });

  it('does not take a document for its claimed type when its name says otherwise', () => {
    // The server decides on content; the page must not promise more than a name can.
    expect(acceptedFiles([file('setup.exe', 'application/pdf')], PUBLISHED)).toEqual([]);
  });

  it('reads the extension of the LAST dot, and none for a name without one', () => {
    expect(acceptedFiles([file('archive.pdf.exe'), file('pdf')], PUBLISHED)).toEqual([]);
    expect(acceptedFiles([file('v1.2.notes.md')], PUBLISHED)).toHaveLength(1);
  });
});
