import type { ExtractedField } from './types';

// Hardcoded OCR-like extractions for the sample PDF.
// Bboxes are normalized (0–1) relative to page size; origin top-left.
export const SAMPLE_PDF_URL = '/sample/ADA146693.pdf';

export const MOCK_EXTRACTED_FIELDS: ExtractedField[] = [
  {
    id: '1',
    key: 'Report number',
    value: 'Research Product 84-03',
    pageIndex: 0,
    bbox: { x: 0.12, y: 0.22, width: 0.35, height: 0.04 },
  },
  {
    id: '2',
    key: 'Date',
    value: 'February 1984',
    pageIndex: 0,
    bbox: { x: 0.35, y: 0.72, width: 0.28, height: 0.035 },
  },
];

