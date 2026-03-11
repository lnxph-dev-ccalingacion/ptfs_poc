// Normalized bbox: 0-1 relative to page width/height (left, top, width, height)
export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ExtractedField {
  id: string;
  key: string;
  value: string;
  pageIndex: number; // 0-based
  bbox: BBox;
  /** Optional rule (e.g. validation or extraction rule) for human-added fields */
  rule?: string;
}
