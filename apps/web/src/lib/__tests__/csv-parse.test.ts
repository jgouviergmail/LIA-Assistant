/**
 * RFC 4180 CSV parser for the document viewer — quoted fields, embedded
 * commas/newlines/quotes, BOM stripping, CRLF tolerance. The generated CSVs
 * come from the backend's stdlib writer (utf-8-sig), so the BOM and quoting
 * cases are not theoretical.
 */

import { describe, it, expect } from 'vitest';

import { parseCsv } from '../csv-parse';

describe('parseCsv', () => {
  it('parses a plain table', () => {
    expect(parseCsv('a,b\n1,2\n3,4')).toEqual([
      ['a', 'b'],
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('strips the utf-8 BOM the backend writes for Excel', () => {
    expect(parseCsv('﻿modèle,prix\nFable 5,20')).toEqual([
      ['modèle', 'prix'],
      ['Fable 5', '20'],
    ]);
  });

  it('honours quoted fields with commas, quotes and newlines', () => {
    const raw = 'name,note\n"Doe, Jane","she said ""hi""\nsecond line"';
    expect(parseCsv(raw)).toEqual([
      ['name', 'note'],
      ['Doe, Jane', 'she said "hi"\nsecond line'],
    ]);
  });

  it('tolerates CRLF line endings', () => {
    expect(parseCsv('a,b\r\n1,2\r\n')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });

  it('keeps empty cells and returns no phantom trailing row', () => {
    expect(parseCsv('a,,c\n,,\n')).toEqual([
      ['a', '', 'c'],
      ['', '', ''],
    ]);
  });

  it('returns an empty array for empty input', () => {
    expect(parseCsv('')).toEqual([]);
    expect(parseCsv('﻿')).toEqual([]);
  });
});
