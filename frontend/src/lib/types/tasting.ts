/**
 * Types for batch tasting notes.
 */

/** Tasting note record from the API */
export interface TastingNote {
  id: number;
  batch_id: number;
  user_id?: string;
  tasted_at: string;
  days_since_packaging?: number;
  serving_temp_c?: number;
  glassware?: string;
  appearance_score?: number;
  appearance_notes?: string;
  aroma_score?: number;
  aroma_notes?: string;
  flavor_score?: number;
  flavor_notes?: string;
  mouthfeel_score?: number;
  mouthfeel_notes?: string;
  overall_score?: number;
  overall_notes?: string;
  total_score?: number;
  to_style?: boolean;
  style_deviation_notes?: string;
  ai_suggestions?: string;
  interview_transcript?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** Score category keys for iteration */
export type ScoreCategory = 'appearance' | 'aroma' | 'flavor' | 'mouthfeel' | 'overall';

/** Score category display info */
export interface ScoreCategoryInfo {
  name: string;
  abbrev: string;
  maxScore: number;
}

/** Map of score category to display info */
export const SCORE_CATEGORIES: Record<ScoreCategory, ScoreCategoryInfo> = {
  appearance: { name: 'Appearance', abbrev: 'A', maxScore: 5 },
  aroma: { name: 'Aroma', abbrev: 'R', maxScore: 5 },
  flavor: { name: 'Flavor', abbrev: 'F', maxScore: 5 },
  mouthfeel: { name: 'Mouthfeel', abbrev: 'M', maxScore: 5 },
  overall: { name: 'Overall', abbrev: 'O', maxScore: 5 }
};

/** Maximum total score (sum of all category max scores) */
export const MAX_TOTAL_SCORE = 25;
