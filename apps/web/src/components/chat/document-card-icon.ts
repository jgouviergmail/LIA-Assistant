/**
 * Lucide icon for a generated document, by format family (ADR-226).
 * Shared by the chat card and the document viewer page — one mapping,
 * no drift between the two surfaces.
 */

import { FileSpreadsheet, FileText, Presentation, type LucideIcon } from 'lucide-react';

export function documentTypeIcon(docType: string): LucideIcon {
  switch (docType) {
    case 'csv':
    case 'xlsx':
      return FileSpreadsheet;
    case 'pptx':
      return Presentation;
    default:
      return FileText;
  }
}
