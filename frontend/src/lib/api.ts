// API helper functions for BrewSignal

const BASE_URL = '/api';

export interface HistoricalReading {
	id: number;
	timestamp: string;
	sg_raw: number | null;
	sg_calibrated: number | null;
	temp_raw: number | null;
	temp_calibrated: number | null;
	rssi: number | null;
	status?: string; // 'valid', 'invalid', 'uncalibrated', 'incomplete'
	// Battery (GravityMon/iSpindel)
	battery_percent?: number | null;
	// ML fields
	sg_filtered?: number | null;
	temp_filtered?: number | null;
	confidence?: number | null;
	sg_rate?: number | null;
	temp_rate?: number | null;
	is_anomaly?: boolean;
	anomaly_score?: number | null;
	anomaly_reasons?: string | null;
}

export interface TimeRangeOption {
	label: string;
	hours: number;
}

export const TIME_RANGES: TimeRangeOption[] = [
	{ label: '1H', hours: 1 },
	{ label: '6H', hours: 6 },
	{ label: '24H', hours: 24 },
	{ label: '7D', hours: 168 },
	{ label: '30D', hours: 720 },
	{ label: 'All', hours: 0 }
];

export async function fetchReadings(
	deviceId: string,
	hours?: number,
	batchId?: number
): Promise<HistoricalReading[]> {
	const params = new URLSearchParams();
	params.append('limit', '5000');
	if (hours !== undefined && hours > 0) {
		params.append('hours', String(hours));
	}
	if (batchId !== undefined) {
		params.append('batch_id', String(batchId));
	}
	const response = await fetch(`${BASE_URL}/devices/${deviceId}/readings?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch readings: ${response.statusText}`);
	}
	return response.json();
}

export async function updateTiltBeerName(tiltId: string, beerName: string): Promise<void> {
	const response = await fetch(`${BASE_URL}/tilts/${tiltId}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ beer_name: beerName })
	});
	if (!response.ok) {
		throw new Error(`Failed to update tilt: ${response.statusText}`);
	}
}

export interface AmbientHistoricalReading {
	id: number;
	timestamp: string;
	temperature: number | null;
	humidity: number | null;
}

export async function fetchAmbientHistory(hours: number = 24): Promise<AmbientHistoricalReading[]> {
	const response = await fetch(`${BASE_URL}/ambient/history?hours=${hours}`);
	if (!response.ok) {
		throw new Error('Failed to fetch ambient history');
	}
	return response.json();
}

export interface ChamberHistoricalReading {
	id: number;
	timestamp: string;
	temperature: number | null;
	humidity: number | null;
}

export async function fetchChamberHistory(hours: number = 24): Promise<ChamberHistoricalReading[]> {
	const response = await fetch(`${BASE_URL}/chamber/history?hours=${hours}`);
	if (!response.ok) {
		throw new Error('Failed to fetch chamber history');
	}
	return response.json();
}

// ============================================================================
// Batch Types & API
// ============================================================================

export interface MLPredictions {
	available: boolean;
	predicted_fg?: number;
	predicted_og?: number;
	estimated_completion?: string;
	hours_to_completion?: number;
	model_type?: string;
	r_squared?: number;
	num_readings?: number;
	error?: string;
	reason?: string;
}

export async function fetchBatchPredictions(batchId: number): Promise<MLPredictions> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/predictions`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch predictions: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Reload ML predictions from database history
 */
export async function reloadBatchPredictions(batchId: number): Promise<{ success: boolean; readings_loaded: number; message: string }> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/reload-predictions`, {
		method: 'POST'
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to reload predictions');
	}
	return response.json();
}

export type BatchStatus = 'planning' | 'fermenting' | 'conditioning' | 'completed' | 'archived';

export interface FermentableResponse {
	id: number;
	name: string;
	type?: string;
	amount_kg?: number;
	yield_percent?: number;
	color_lovibond?: number;
	origin?: string;
	supplier?: string;
}

export interface HopResponse {
	id: number;
	name: string;
	origin?: string;
	form?: string;
	alpha_acid_percent?: number;
	beta_acid_percent?: number;
	amount_grams?: number;
	timing?: {
		use?: string;
		duration?: {
			value?: number;
			unit?: string;
		};
	};
	format_extensions?: Record<string, unknown>;
}

export interface YeastResponse {
	id: number;
	name: string;
	lab?: string;
	product_id?: string;
	type?: string;
	attenuation_percent?: number;
	temp_min_c?: number;
	temp_max_c?: number;
	flocculation?: string;
}

// BeerJSON calls yeasts "cultures"
export interface CultureResponse {
	id: number;
	name: string;
	producer?: string;  // BeerJSON name for 'lab'
	product_id?: string;
	type?: string;
	form?: string;
	attenuation_min_percent?: number;
	attenuation_max_percent?: number;
	temp_min_c?: number;
	temp_max_c?: number;
	amount?: number;
	amount_unit?: string;
	timing?: Record<string, any>;
	format_extensions?: Record<string, any>;
}

export interface MiscResponse {
	id: number;
	name: string;
	type?: string;
	use?: string;
	time_min?: number;
	amount_kg?: number;
	amount_is_weight?: boolean;
}

export interface RecipeResponse {
	id: number;
	name: string;
	author?: string;
	style_id?: string;
	type?: string;
	// BeerJSON field names (not *_target)
	og?: number;
	fg?: number;
	abv?: number;
	ibu?: number;
	color_srm?: number;
	batch_size_liters?: number;
	boil_time_minutes?: number;
	efficiency_percent?: number;
	carbonation_vols?: number;
	// Yeast info
	yeast_name?: string;
	yeast_lab?: string;
	yeast_product_id?: string;
	yeast_temp_min?: number;
	yeast_temp_max?: number;
	yeast_attenuation?: number;
	notes?: string;
	created_at: string;
	style?: { id: string; name: string };
	format_extensions?: Record<string, unknown>;
	// Ingredient lists (only in detail response)
	fermentables?: FermentableResponse[];
	hops?: HopResponse[];
	cultures?: CultureResponse[];  // BeerJSON uses 'cultures' not 'yeasts'
	miscs?: MiscResponse[];
}

// Yeast Strain types
export interface YeastStrainResponse {
	id: number;
	name: string;
	producer?: string;
	product_id?: string;
	type?: string;  // ale, lager, wine, wild, hybrid
	form?: string;  // dry, liquid, slant
	attenuation_low?: number;
	attenuation_high?: number;
	temp_low?: number;  // Celsius
	temp_high?: number;  // Celsius
	alcohol_tolerance?: number;
	flocculation?: string;  // low, medium, high, very_high
	description?: string;
	source: string;
	is_custom: boolean;
	created_at: string;
	updated_at: string;
}

export interface YeastStrainCreate {
	name: string;
	producer?: string;
	product_id?: string;
	type?: string;
	form?: string;
	attenuation_low?: number;
	attenuation_high?: number;
	temp_low?: number;
	temp_high?: number;
	alcohol_tolerance?: number;
	flocculation?: string;
	description?: string;
}

// Hop Variety types
export interface HopVarietyResponse {
	id: number;
	name: string;
	origin?: string;
	alpha_acid_low?: number;
	alpha_acid_high?: number;
	beta_acid_low?: number;
	beta_acid_high?: number;
	purpose?: string;  // bittering, aroma, dual
	aroma_profile?: string;
	substitutes?: string;
	description?: string;
	source: string;
	is_custom: boolean;
	created_at: string;
	updated_at: string;
}

export interface HopVarietyCreate {
	name: string;
	origin?: string;
	alpha_acid_low?: number;
	alpha_acid_high?: number;
	beta_acid_low?: number;
	beta_acid_high?: number;
	purpose?: string;
	aroma_profile?: string;
	substitutes?: string;
	description?: string;
}

export interface HopVarietyFilters {
	origin?: string;
	purpose?: string;
	search?: string;
	is_custom?: boolean;
	limit?: number;
	offset?: number;
}

export interface BatchResponse {
	id: number;
	recipe_id?: number;
	device_id?: string;
	yeast_strain_id?: number;
	batch_number?: number;
	name?: string;
	status: BatchStatus;
	brew_date?: string;
	start_time?: string;
	end_time?: string;
	measured_og?: number;
	measured_fg?: number;
	measured_abv?: number;
	measured_attenuation?: number;
	notes?: string;
	created_at: string;
	recipe?: RecipeResponse;
	yeast_strain?: YeastStrainResponse;
	// Temperature control
	heater_entity_id?: string;
	cooler_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
	// Soft delete
	deleted_at?: string;
}

export interface BatchCreate {
	recipe_id?: number;
	device_id?: string;
	yeast_strain_id?: number;
	name?: string;
	status?: BatchStatus;
	brew_date?: string;
	measured_og?: number;
	notes?: string;
	// Temperature control
	heater_entity_id?: string;
	cooler_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
}

export interface BatchUpdate {
	name?: string;
	status?: BatchStatus;
	device_id?: string;
	recipe_id?: number;
	yeast_strain_id?: number;
	brew_date?: string;
	start_time?: string;
	end_time?: string;
	measured_og?: number;
	measured_fg?: number;
	notes?: string;
	// Temperature control
	heater_entity_id?: string;
	cooler_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
}

export interface BatchProgressResponse {
	batch_id: number;
	recipe_name?: string;
	status: BatchStatus;
	targets: {
		og?: number;
		fg?: number;
		attenuation?: number;
		abv?: number;
	};
	measured: {
		og?: number;
		current_sg?: number;
		attenuation?: number;
		abv?: number;
	};
	progress: {
		percent_complete?: number;
		sg_remaining?: number;
		estimated_days_remaining?: number;
	};
	temperature: {
		current?: number;
		yeast_min?: number;
		yeast_max?: number;
		status: 'unknown' | 'in_range' | 'too_cold' | 'too_hot';
	};
}

export interface BatchControlStatus {
	batch_id: number;
	enabled: boolean;
	heater_state?: string;
	heater_entity?: string;
	cooler_state?: string;
	cooler_entity?: string;
	override_active: boolean;
	override_state?: string;
	override_until?: string;
	target_temp?: number;
	hysteresis?: number;
	wort_temp?: number;
}

/**
 * Heater entity from Home Assistant
 */
export interface HeaterEntity {
	entity_id: string;
	friendly_name: string;
	state: string | null;
}

/**
 * Override request for heater or cooler control
 */
export interface OverrideRequest {
	device_type?: string; // "heater" or "cooler" (defaults to "heater")
	state: string | null;
	duration_minutes?: number;
	batch_id?: number;
}

/**
 * Fetch available heater entities from Home Assistant
 */
export async function fetchHeaterEntities(): Promise<HeaterEntity[]> {
	const response = await fetch(`${BASE_URL}/control/heater-entities`);
	if (!response.ok) {
		throw new Error(`Failed to fetch heater entities: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch available cooler entities from Home Assistant
 */
export async function fetchCoolerEntities(): Promise<HeaterEntity[]> {
	const response = await fetch(`${BASE_URL}/control/cooler-entities`);
	if (!response.ok) {
		throw new Error(`Failed to fetch cooler entities: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch batch control status
 */
export async function fetchBatchControlStatus(batchId: number): Promise<BatchControlStatus> {
	const response = await fetch(`${BASE_URL}/control/batch/${batchId}/status`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch control status: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Toggle heater for a specific batch
 */
export async function toggleBatchHeater(batchId: number, state: 'on' | 'off'): Promise<{ success: boolean; message: string; new_state?: string }> {
	const response = await fetch(`${BASE_URL}/control/heater`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ state, batch_id: batchId })
	});
	return response.json();
}

/**
 * Set heater override for a batch
 */
export async function setBatchHeaterOverride(
	batchId: number,
	state: 'on' | 'off' | null,
	durationMinutes: number = 60,
	deviceType: string = 'heater'
): Promise<{ success: boolean; message: string; override_state?: string; override_until?: string }> {
	const response = await fetch(`${BASE_URL}/control/override`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			state,
			duration_minutes: durationMinutes,
			batch_id: batchId,
			device_type: deviceType
		})
	});
	return response.json();
}

/**
 * Fetch batches with optional filtering
 */
export async function fetchBatches(
	status?: BatchStatus,
	deviceId?: string,
	limit: number = 50,
	offset: number = 0,
	deletedOnly: boolean = false
): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	if (status) params.append('status', status);
	if (deviceId) params.append('device_id', deviceId);
	if (deletedOnly) params.append('deleted_only', 'true');
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch active batches (planning or fermenting)
 */
export async function fetchActiveBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches/active?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch active batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch completed batches (completed or conditioning)
 */
export async function fetchCompletedBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches/completed?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch completed batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch deleted batches
 */
export async function fetchDeletedBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	return fetchBatches(undefined, undefined, limit, offset, true);
}

/**
 * Fetch a single batch by ID
 */
export async function fetchBatch(batchId: number): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Create a new batch
 */
export async function createBatch(batch: BatchCreate): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(batch)
	});
	if (!response.ok) {
		throw new Error(`Failed to create batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Update an existing batch
 */
export async function updateBatch(batchId: number, update: BatchUpdate): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(update)
	});
	if (!response.ok) {
		throw new Error(`Failed to update batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Delete a batch (soft delete by default, hard delete optional)
 */
export async function deleteBatch(batchId: number, hardDelete: boolean = false): Promise<void> {
	const url = `${BASE_URL}/batches/${batchId}/delete`;
	const urlWithParams = hardDelete ? `${url}?hard_delete=true` : url;
	const response = await fetch(urlWithParams, {
		method: 'POST'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete batch: ${response.statusText}`);
	}
}

/**
 * Restore a soft-deleted batch
 */
export async function restoreBatch(batchId: number): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/restore`, {
		method: 'POST'
	});
	if (!response.ok) {
		throw new Error(`Failed to restore batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch fermentation progress for a batch
 */
export async function fetchBatchProgress(batchId: number): Promise<BatchProgressResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/progress`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch progress: ${response.statusText}`);
	}
	return response.json();
}

// ============================================================================
// Recipe Types & API
// ============================================================================

export async function fetchRecipes(limit = 50, offset = 0): Promise<RecipeResponse[]> {
	const response = await fetch(`${BASE_URL}/recipes?limit=${limit}&offset=${offset}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to fetch recipes');
	}
	return response.json();
}

export async function fetchRecipe(id: number): Promise<RecipeResponse> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to fetch recipe');
	}
	return response.json();
}

export interface RecipeCreate {
	name: string;
	author?: string;
	style_id?: string;
	type?: string;
	og?: number;
	fg?: number;
	abv?: number;
	ibu?: number;
	color_srm?: number;
	batch_size_liters?: number;
	boil_time_minutes?: number;
	efficiency_percent?: number;
	carbonation_vols?: number;
	yeast_name?: string;
	yeast_lab?: string;
	yeast_product_id?: string;
	yeast_temp_min?: number;
	yeast_temp_max?: number;
	yeast_attenuation?: number;
	notes?: string;
	format_extensions?: Record<string, any>;
}

export interface RecipeUpdateData {
	name?: string;
	author?: string;
	style_id?: string;
	type?: string;
	og?: number;
	fg?: number;
	abv?: number;
	ibu?: number;
	color_srm?: number;
	batch_size_liters?: number;
	boil_time_minutes?: number;
	efficiency_percent?: number;
	carbonation_vols?: number;
	yeast_name?: string;
	yeast_lab?: string;
	yeast_product_id?: string;
	yeast_temp_min?: number;
	yeast_temp_max?: number;
	yeast_attenuation?: number;
	notes?: string;
	format_extensions?: Record<string, any>;
}

export async function createRecipe(recipe: RecipeCreate): Promise<RecipeResponse> {
	const response = await fetch(`${BASE_URL}/recipes`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(recipe)
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		// Handle both string and array error formats from backend
		const detail = Array.isArray(error.detail) ? error.detail.join('; ') : error.detail;
		throw new Error(detail || 'Failed to create recipe');
	}

	return response.json();
}

export async function updateRecipe(id: number, recipe: RecipeUpdateData): Promise<RecipeResponse> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(recipe)
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		// Handle both string and array error formats from backend
		const detail = Array.isArray(error.detail) ? error.detail.join('; ') : error.detail;
		throw new Error(detail || 'Failed to update recipe');
	}

	return response.json();
}

/**
 * Import recipe from BeerXML, BeerJSON, or Brewfather JSON.
 * Backend auto-detects format from file extension and content.
 *
 * @param file - Recipe file (.xml or .json)
 * @returns Array of imported recipes (typically single recipe)
 * @throws Error with backend validation message if import fails
 */
export async function importRecipe(file: File): Promise<RecipeResponse[]> {
	const formData = new FormData();
	formData.append('file', file);

	const response = await fetch(`${BASE_URL}/recipes/import`, {
		method: 'POST',
		body: formData
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		// Handle both string and array error formats from backend
		const detail = Array.isArray(error.detail) ? error.detail.join('; ') : error.detail;
		throw new Error(detail || 'Failed to import recipe');
	}

	return response.json();
}

export async function deleteRecipe(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`, {
		method: 'DELETE'
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to delete recipe');
	}
}

// ============================================================================
// Maintenance Types & API
// ============================================================================

export interface OrphanedDataReport {
	orphaned_readings_count: number;
	orphaned_readings: number[]; // Reading IDs
	batches_with_orphans: Record<number, number>; // batch_id -> count
}

export interface CleanupPreview {
	readings_to_delete: number[]; // Reading IDs
	total_count: number;
	batch_breakdown: Record<number, number>; // batch_id -> count
}

/**
 * Fetch orphaned data report (readings linked to deleted batches)
 */
export async function fetchOrphanedData(): Promise<OrphanedDataReport> {
	const response = await fetch(`${BASE_URL}/maintenance/orphaned-data`);
	if (!response.ok) {
		throw new Error(`Failed to fetch orphaned data: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Preview cleanup of readings for deleted batches
 */
export async function previewCleanup(batchIds: number[]): Promise<CleanupPreview> {
	const response = await fetch(`${BASE_URL}/maintenance/cleanup-readings`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ deleted_batch_ids: batchIds, dry_run: true })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to preview cleanup');
	}
	return response.json();
}

/**
 * Execute cleanup of readings for deleted batches
 */
export async function executeCleanup(batchIds: number[]): Promise<CleanupPreview> {
	const response = await fetch(`${BASE_URL}/maintenance/cleanup-readings`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ deleted_batch_ids: batchIds, dry_run: false })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to execute cleanup');
	}
	return response.json();
}

// ============================================================================
// Control Events Types & API
// ============================================================================

export interface ControlEvent {
	id: number;
	timestamp: string;
	device_id?: string;
	batch_id?: number;
	action: string; // 'heat_on', 'heat_off', 'cool_on', 'cool_off'
	wort_temp?: number | null; // Temperature in Celsius
	ambient_temp?: number | null; // Temperature in Celsius
	target_temp?: number | null; // Temperature in Celsius
}

/**
 * Fetch control event history for a batch
 */
export async function fetchBatchControlEvents(
	batchId: number,
	hours: number = 24
): Promise<ControlEvent[]> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/control-events?hours=${hours}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch control events: ${response.statusText}`);
	}
	return response.json();
}

// ============================================================================
// Yeast Strain API
// ============================================================================

export interface YeastStrainFilters {
	type?: string;
	producer?: string;
	form?: string;
	search?: string;
	is_custom?: boolean;
	limit?: number;
	offset?: number;
}

/**
 * Fetch yeast strains with optional filters
 */
export async function fetchYeastStrains(filters?: YeastStrainFilters): Promise<YeastStrainResponse[]> {
	const params = new URLSearchParams();
	if (filters?.type) params.append('type', filters.type);
	if (filters?.producer) params.append('producer', filters.producer);
	if (filters?.form) params.append('form', filters.form);
	if (filters?.search) params.append('search', filters.search);
	if (filters?.is_custom !== undefined) params.append('is_custom', String(filters.is_custom));
	if (filters?.limit) params.append('limit', String(filters.limit));
	if (filters?.offset) params.append('offset', String(filters.offset));

	const response = await fetch(`${BASE_URL}/yeast-strains?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast strains: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch a single yeast strain by ID
 */
export async function fetchYeastStrain(id: number): Promise<YeastStrainResponse> {
	const response = await fetch(`${BASE_URL}/yeast-strains/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast strain: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch yeast strain statistics
 */
export async function fetchYeastStrainStats(): Promise<{ total: number; custom: number; seeded: number }> {
	const response = await fetch(`${BASE_URL}/yeast-strains/stats`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast strain stats: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch list of unique producers
 */
export async function fetchYeastProducers(): Promise<{ producers: string[] }> {
	const response = await fetch(`${BASE_URL}/yeast-strains/producers`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast producers: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Create a custom yeast strain
 */
export async function createYeastStrain(strain: YeastStrainCreate): Promise<YeastStrainResponse> {
	const response = await fetch(`${BASE_URL}/yeast-strains`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(strain)
	});
	if (!response.ok) {
		throw new Error(`Failed to create yeast strain: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Delete a custom yeast strain
 */
export async function deleteYeastStrain(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/yeast-strains/${id}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete yeast strain: ${response.statusText}`);
	}
}

/**
 * Refresh yeast strains from seed file
 */
export async function refreshYeastStrains(): Promise<{
	success: boolean;
	action: string;
	count?: number;
	version?: string;
}> {
	const response = await fetch(`${BASE_URL}/yeast-strains/refresh`, {
		method: 'POST'
	});
	if (!response.ok) {
		throw new Error(`Failed to refresh yeast strains: ${response.statusText}`);
	}
	return response.json();
}

// ============================================================================
// Hop Variety API
// ============================================================================

/**
 * Fetch hop varieties with optional filters
 */
export async function fetchHopVarieties(filters?: HopVarietyFilters): Promise<HopVarietyResponse[]> {
	const params = new URLSearchParams();
	if (filters?.origin) params.append('origin', filters.origin);
	if (filters?.purpose) params.append('purpose', filters.purpose);
	if (filters?.search) params.append('search', filters.search);
	if (filters?.is_custom !== undefined) params.append('is_custom', String(filters.is_custom));
	if (filters?.limit) params.append('limit', String(filters.limit));
	if (filters?.offset) params.append('offset', String(filters.offset));

	const response = await fetch(`${BASE_URL}/hop-varieties?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop varieties: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch a single hop variety by ID
 */
export async function fetchHopVariety(id: number): Promise<HopVarietyResponse> {
	const response = await fetch(`${BASE_URL}/hop-varieties/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop variety: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch hop variety statistics
 */
export async function fetchHopVarietyStats(): Promise<{ total: number; custom: number; seeded: number }> {
	const response = await fetch(`${BASE_URL}/hop-varieties/stats`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop variety stats: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch list of unique hop origins
 */
export async function fetchHopOrigins(): Promise<{ origins: string[] }> {
	const response = await fetch(`${BASE_URL}/hop-varieties/origins`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop origins: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Create a custom hop variety
 */
export async function createHopVariety(variety: HopVarietyCreate): Promise<HopVarietyResponse> {
	const response = await fetch(`${BASE_URL}/hop-varieties`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(variety)
	});
	if (!response.ok) {
		throw new Error(`Failed to create hop variety: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Delete a custom hop variety
 */
export async function deleteHopVariety(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/hop-varieties/${id}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete hop variety: ${response.statusText}`);
	}
}

/**
 * Refresh hop varieties from seed file
 */
export async function refreshHopVarieties(): Promise<{
	success: boolean;
	action: string;
	count?: number;
	version?: string;
}> {
	const response = await fetch(`${BASE_URL}/hop-varieties/refresh`, {
		method: 'POST'
	});
	if (!response.ok) {
		throw new Error(`Failed to refresh hop varieties: ${response.statusText}`);
	}
	return response.json();
}

// ============================================================================
// Inventory Types & API
// ============================================================================

// Equipment Types
export type EquipmentType =
	| 'kettle'
	| 'fermenter'
	| 'pump'
	| 'chiller'
	| 'mill'
	| 'mash_tun'
	| 'lauter_tun'
	| 'hot_liquor_tank'
	| 'bottling'
	| 'kegging'
	| 'all_in_one'
	| 'other';

export interface EquipmentResponse {
	id: number;
	name: string;
	type: EquipmentType;
	brand?: string;
	model?: string;
	capacity_liters?: number;
	capacity_kg?: number;
	is_active: boolean;
	notes?: string;
	created_at: string;
	updated_at: string;
}

export interface EquipmentCreate {
	name: string;
	type: EquipmentType;
	brand?: string;
	model?: string;
	capacity_liters?: number;
	capacity_kg?: number;
	is_active?: boolean;
	notes?: string;
}

export interface EquipmentUpdate {
	name?: string;
	type?: EquipmentType;
	brand?: string;
	model?: string;
	capacity_liters?: number;
	capacity_kg?: number;
	is_active?: boolean;
	notes?: string;
}

// Hop Inventory Types
export type HopForm = 'pellet' | 'leaf' | 'plug';

export interface HopInventoryResponse {
	id: number;
	variety: string;
	amount_grams: number;
	alpha_acid_percent?: number;
	crop_year?: number;
	form: HopForm;
	storage_location?: string;
	purchase_date?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
	created_at: string;
	updated_at: string;
}

export interface HopInventoryCreate {
	variety: string;
	amount_grams: number;
	alpha_acid_percent?: number;
	crop_year?: number;
	form?: HopForm;
	storage_location?: string;
	purchase_date?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
}

export interface HopInventoryUpdate {
	variety?: string;
	amount_grams?: number;
	alpha_acid_percent?: number;
	crop_year?: number;
	form?: HopForm;
	storage_location?: string;
	purchase_date?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
}

export interface HopSummary {
	total_items: number;
	total_grams: number;
	unique_varieties: number;
}

// Yeast Inventory Types
export type YeastInventoryForm = 'dry' | 'liquid' | 'slant' | 'harvested';

export interface YeastInventoryResponse {
	id: number;
	yeast_strain_id?: number;
	custom_name?: string;
	quantity: number;
	form: YeastInventoryForm;
	manufacture_date?: string;
	expiry_date?: string;
	generation?: number;
	source_batch_id?: number;
	storage_location?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
	created_at: string;
	updated_at: string;
	yeast_strain?: YeastStrainResponse;
}

export interface YeastInventoryCreate {
	yeast_strain_id?: number;
	custom_name?: string;
	quantity?: number;
	form: YeastInventoryForm;
	manufacture_date?: string;
	expiry_date?: string;
	generation?: number;
	source_batch_id?: number;
	storage_location?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
}

export interface YeastInventoryUpdate {
	yeast_strain_id?: number;
	custom_name?: string;
	quantity?: number;
	form?: YeastInventoryForm;
	manufacture_date?: string;
	expiry_date?: string;
	generation?: number;
	source_batch_id?: number;
	storage_location?: string;
	supplier?: string;
	lot_number?: string;
	notes?: string;
}

export interface YeastInventorySummary {
	total_items: number;
	total_quantity: number;
	expiring_soon: number;
	expired: number;
}

// Equipment API
export async function fetchEquipment(params?: {
	type?: EquipmentType;
	is_active?: boolean;
	limit?: number;
	offset?: number;
}): Promise<EquipmentResponse[]> {
	const urlParams = new URLSearchParams();
	if (params?.type) urlParams.append('type', params.type);
	if (params?.is_active !== undefined) urlParams.append('is_active', String(params.is_active));
	if (params?.limit) urlParams.append('limit', String(params.limit));
	if (params?.offset) urlParams.append('offset', String(params.offset));

	const response = await fetch(`${BASE_URL}/inventory/equipment?${urlParams}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch equipment: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchEquipmentTypes(): Promise<string[]> {
	const response = await fetch(`${BASE_URL}/inventory/equipment/types`);
	if (!response.ok) {
		throw new Error(`Failed to fetch equipment types: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchEquipmentItem(id: number): Promise<EquipmentResponse> {
	const response = await fetch(`${BASE_URL}/inventory/equipment/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch equipment: ${response.statusText}`);
	}
	return response.json();
}

export async function createEquipment(equipment: EquipmentCreate): Promise<EquipmentResponse> {
	const response = await fetch(`${BASE_URL}/inventory/equipment`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(equipment)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to create equipment');
	}
	return response.json();
}

export async function updateEquipment(id: number, equipment: EquipmentUpdate): Promise<EquipmentResponse> {
	const response = await fetch(`${BASE_URL}/inventory/equipment/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(equipment)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to update equipment');
	}
	return response.json();
}

export async function deleteEquipment(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/inventory/equipment/${id}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete equipment: ${response.statusText}`);
	}
}

// Hop Inventory API
export async function fetchHopInventory(params?: {
	variety?: string;
	form?: HopForm;
	min_amount_grams?: number;
	limit?: number;
	offset?: number;
}): Promise<HopInventoryResponse[]> {
	const urlParams = new URLSearchParams();
	if (params?.variety) urlParams.append('variety', params.variety);
	if (params?.form) urlParams.append('form', params.form);
	if (params?.min_amount_grams !== undefined) urlParams.append('min_amount_grams', String(params.min_amount_grams));
	if (params?.limit) urlParams.append('limit', String(params.limit));
	if (params?.offset) urlParams.append('offset', String(params.offset));

	const response = await fetch(`${BASE_URL}/inventory/hops?${urlParams}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop inventory: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchHopSummary(): Promise<HopSummary> {
	const response = await fetch(`${BASE_URL}/inventory/hops/summary`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop summary: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchHopItem(id: number): Promise<HopInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/hops/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch hop: ${response.statusText}`);
	}
	return response.json();
}

export async function createHopInventory(hop: HopInventoryCreate): Promise<HopInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/hops`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(hop)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to create hop inventory');
	}
	return response.json();
}

export async function updateHopInventory(id: number, hop: HopInventoryUpdate): Promise<HopInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/hops/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(hop)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to update hop inventory');
	}
	return response.json();
}

export async function adjustHopAmount(id: number, delta_grams: number): Promise<HopInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/hops/${id}/adjust`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ delta_grams })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to adjust hop amount');
	}
	return response.json();
}

export async function deleteHopInventory(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/inventory/hops/${id}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete hop: ${response.statusText}`);
	}
}

// Yeast Inventory API
export async function fetchYeastInventory(params?: {
	query?: string;
	form?: YeastInventoryForm;
	include_expired?: boolean;
	limit?: number;
	offset?: number;
}): Promise<YeastInventoryResponse[]> {
	const urlParams = new URLSearchParams();
	if (params?.query) urlParams.append('query', params.query);
	if (params?.form) urlParams.append('form', params.form);
	if (params?.include_expired !== undefined) urlParams.append('include_expired', String(params.include_expired));
	if (params?.limit) urlParams.append('limit', String(params.limit));
	if (params?.offset) urlParams.append('offset', String(params.offset));

	const response = await fetch(`${BASE_URL}/inventory/yeast?${urlParams}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast inventory: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchExpiringYeast(days: number = 30): Promise<YeastInventoryResponse[]> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/expiring-soon?days=${days}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch expiring yeast: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchYeastInventorySummary(): Promise<YeastInventorySummary> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/summary`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast summary: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchYeastInventoryItem(id: number): Promise<YeastInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch yeast: ${response.statusText}`);
	}
	return response.json();
}

export async function createYeastInventory(yeast: YeastInventoryCreate): Promise<YeastInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/yeast`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(yeast)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to create yeast inventory');
	}
	return response.json();
}

export async function updateYeastInventory(id: number, yeast: YeastInventoryUpdate): Promise<YeastInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(yeast)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to update yeast inventory');
	}
	return response.json();
}

export async function useYeast(id: number, quantity: number = 1): Promise<YeastInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/${id}/use`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ quantity })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to use yeast');
	}
	return response.json();
}

export async function harvestYeast(source_batch_id: number, quantity: number = 1, notes?: string): Promise<YeastInventoryResponse> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/harvest`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ source_batch_id, quantity, notes })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to harvest yeast');
	}
	return response.json();
}

export async function deleteYeastInventory(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/inventory/yeast/${id}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete yeast: ${response.statusText}`);
	}
}
