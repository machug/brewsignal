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
  // BJCP v2 scoring
  scoring_version?: number;  // 1=legacy, 2=BJCP
  aroma_malt?: number;
  aroma_hops?: number;
  aroma_fermentation?: number;
  aroma_other?: number;
  appearance_color?: number;
  appearance_clarity?: number;
  appearance_head?: number;
  flavor_malt?: number;
  flavor_hops?: number;
  flavor_bitterness?: number;
  flavor_fermentation?: number;
  flavor_balance?: number;
  flavor_finish?: number;
  mouthfeel_body?: number;
  mouthfeel_carbonation?: number;
  mouthfeel_warmth?: number;
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

export interface BJCPSubcategory {
  key: string;
  name: string;
  maxScore: number;
}

export interface BJCPCategory {
  name: string;
  key: string;
  maxScore: number;
  notesKey: string;
  subcategories: BJCPSubcategory[];
}

export const BJCP_CATEGORIES: BJCPCategory[] = [
  {
    name: 'Aroma', key: 'aroma', maxScore: 12, notesKey: 'aroma_notes',
    subcategories: [
      { key: 'aroma_malt', name: 'Malt', maxScore: 3 },
      { key: 'aroma_hops', name: 'Hops', maxScore: 3 },
      { key: 'aroma_fermentation', name: 'Fermentation', maxScore: 3 },
      { key: 'aroma_other', name: 'Other', maxScore: 3 },
    ]
  },
  {
    name: 'Appearance', key: 'appearance', maxScore: 3, notesKey: 'appearance_notes',
    subcategories: [
      { key: 'appearance_color', name: 'Color', maxScore: 1 },
      { key: 'appearance_clarity', name: 'Clarity', maxScore: 1 },
      { key: 'appearance_head', name: 'Head', maxScore: 1 },
    ]
  },
  {
    name: 'Flavor', key: 'flavor', maxScore: 20, notesKey: 'flavor_notes',
    subcategories: [
      { key: 'flavor_malt', name: 'Malt', maxScore: 5 },
      { key: 'flavor_hops', name: 'Hops', maxScore: 5 },
      { key: 'flavor_bitterness', name: 'Bitterness', maxScore: 3 },
      { key: 'flavor_fermentation', name: 'Fermentation', maxScore: 3 },
      { key: 'flavor_balance', name: 'Balance', maxScore: 2 },
      { key: 'flavor_finish', name: 'Finish/Aftertaste', maxScore: 2 },
    ]
  },
  {
    name: 'Mouthfeel', key: 'mouthfeel', maxScore: 5, notesKey: 'mouthfeel_notes',
    subcategories: [
      { key: 'mouthfeel_body', name: 'Body', maxScore: 2 },
      { key: 'mouthfeel_carbonation', name: 'Carbonation', maxScore: 2 },
      { key: 'mouthfeel_warmth', name: 'Warmth', maxScore: 1 },
    ]
  },
  {
    name: 'Overall', key: 'overall', maxScore: 10, notesKey: 'overall_notes',
    subcategories: []  // Single overall_score field (0-10)
  },
];

export const BJCP_MAX_TOTAL = 50;

export function getBJCPRating(score: number): string {
  if (score >= 45) return 'Outstanding';
  if (score >= 38) return 'Excellent';
  if (score >= 30) return 'Very Good';
  if (score >= 21) return 'Good';
  if (score >= 14) return 'Fair';
  return 'Problematic';
}
