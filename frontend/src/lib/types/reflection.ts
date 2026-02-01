/**
 * Types for batch phase reflections.
 */

/** Valid phases for batch reflections */
export type ReflectionPhase = 'brew_day' | 'fermentation' | 'packaging' | 'conditioning';

/** Batch reflection record from the API */
export interface BatchReflection {
  id: number;
  batch_id: number;
  user_id?: string;
  phase: ReflectionPhase;
  created_at: string;
  updated_at: string;
  metrics?: Record<string, number>;
  what_went_well?: string;
  what_went_wrong?: string;
  lessons_learned?: string;
  next_time_changes?: string;
  ai_summary?: string;
  ai_generated_at?: string;
  ai_model_version?: string;
}

/** Phase display metadata */
export interface PhaseInfo {
  name: string;
  icon: string;
}

/** Map of phase to display info */
export const PHASE_INFO: Record<ReflectionPhase, PhaseInfo> = {
  brew_day: { name: 'Brew Day', icon: '🍺' },
  fermentation: { name: 'Fermentation', icon: '🫧' },
  packaging: { name: 'Packaging', icon: '📦' },
  conditioning: { name: 'Conditioning', icon: '❄️' }
};

/** Metric keys by phase for display purposes */
export const PHASE_METRICS: Record<ReflectionPhase, string[]> = {
  brew_day: [
    'mash_temp',
    'mash_duration_min',
    'pre_boil_sg',
    'pre_boil_volume_l',
    'post_boil_sg',
    'post_boil_volume_l',
    'efficiency_percent',
    'boil_duration_min'
  ],
  fermentation: [
    'pitch_temp',
    'pitch_rate',
    'peak_temp',
    'days_in_primary',
    'gravity_at_transfer'
  ],
  packaging: [
    'final_gravity',
    'volumes_co2',
    'priming_sugar_g',
    'bottles_filled',
    'kegs_filled'
  ],
  conditioning: [
    'conditioning_days',
    'conditioning_temp',
    'carbonation_level'
  ]
};

/** Human-readable labels for metric keys */
export const METRIC_LABELS: Record<string, string> = {
  mash_temp: 'Mash Temperature',
  mash_duration_min: 'Mash Duration (min)',
  pre_boil_sg: 'Pre-Boil SG',
  pre_boil_volume_l: 'Pre-Boil Volume (L)',
  post_boil_sg: 'Post-Boil SG',
  post_boil_volume_l: 'Post-Boil Volume (L)',
  efficiency_percent: 'Efficiency (%)',
  boil_duration_min: 'Boil Duration (min)',
  pitch_temp: 'Pitch Temperature',
  pitch_rate: 'Pitch Rate',
  peak_temp: 'Peak Temperature',
  days_in_primary: 'Days in Primary',
  gravity_at_transfer: 'Gravity at Transfer',
  final_gravity: 'Final Gravity',
  volumes_co2: 'Volumes CO2',
  priming_sugar_g: 'Priming Sugar (g)',
  bottles_filled: 'Bottles Filled',
  kegs_filled: 'Kegs Filled',
  conditioning_days: 'Conditioning Days',
  conditioning_temp: 'Conditioning Temp',
  carbonation_level: 'Carbonation Level'
};
