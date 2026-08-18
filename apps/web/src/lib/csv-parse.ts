/**
 * Minimal RFC 4180 CSV parser for the document viewer.
 *
 * Handles exactly what the backend's stdlib `csv.writer` emits (utf-8-sig):
 * BOM prefix, quoted fields containing commas / escaped quotes / newlines,
 * CRLF or LF endings. No configurable delimiter on purpose — generated CSVs
 * are comma-separated by construction.
 */

export function parseCsv(raw: string): string[][] {
  const text = raw.replace(/^﻿/, '');
  if (text === '') return [];

  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }
  // Final field/row unless the input ended on a line break.
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}
