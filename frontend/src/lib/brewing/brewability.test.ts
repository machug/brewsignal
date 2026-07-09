import { describe, expect, test } from 'vitest';
import { checkBrewability, type BrewabilityWarning } from './brewability';
import type { EquipmentResponse } from '$lib/api';

let nextId = 1;
function gear(partial: Partial<EquipmentResponse> & Pick<EquipmentResponse, 'type'>): EquipmentResponse {
	return {
		id: nextId++,
		name: partial.name ?? `${partial.type} #${nextId}`,
		is_active: true,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...partial,
	};
}

const codes = (warnings: BrewabilityWarning[]) => warnings.map((w) => w.code).sort();

describe('checkBrewability', () => {
	test('no warnings when recipe fits all owned gear', () => {
		// 23 L batch, 5.85 kg grain → mash volume ~20.7 L (Brewfather-calibrated fixture)
		const warnings = checkBrewability(
			{ batch_size_liters: 23, total_grain_kg: 5.85, boil_time_minutes: 60 },
			[
				gear({ type: 'all_in_one', name: 'G40', capacity_liters: 40, capacity_kg: 18 }),
				gear({ type: 'fermenter', name: 'FermZilla', capacity_liters: 30 }),
			],
		);
		expect(warnings).toEqual([]);
	});

	test('flags mash overflow on a 30 L all-in-one with a big grain bill', () => {
		// 21 L batch, 9 kg grain → mash water 9·2.7+1 = 25.3 L + displacement 6.03 L = 31.33 L > 30 L
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 9 },
			[gear({ type: 'all_in_one', name: 'G30', capacity_liters: 30 })],
		);
		const mash = warnings.find((w) => w.code === 'mash_overflow');
		expect(mash).toBeDefined();
		expect(mash!.equipment_name).toBe('G30');
		expect(mash!.required).toBeCloseTo(31.33, 2);
		expect(mash!.available).toBe(30);
	});

	test('flags grain bill over malt pipe capacity_kg', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 10 },
			[gear({ type: 'all_in_one', name: 'BrewZilla 35', capacity_liters: 35, capacity_kg: 9 })],
		);
		expect(codes(warnings)).toContain('grain_over_capacity');
	});

	test('flags pre-boil volume over largest boil vessel', () => {
		// 25 L batch, 60 min boil → pre-boil ≈ 25 + 0.85 + 1 = 26.85 L > 25 L kettle
		const warnings = checkBrewability(
			{ batch_size_liters: 25, total_grain_kg: 5, boil_time_minutes: 60 },
			[
				gear({ type: 'kettle', name: 'Stock pot', capacity_liters: 25 }),
				gear({ type: 'mash_tun', name: 'Big tun', capacity_liters: 50 }),
			],
		);
		expect(codes(warnings)).toContain('boil_overflow');
	});

	test('flags fermenter too small for batch plus krausen headspace', () => {
		// 21 L × 1.2 = 25.2 L needed > 23 L fermenter
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 4 },
			[
				gear({ type: 'all_in_one', name: 'G40', capacity_liters: 40 }),
				gear({ type: 'fermenter', name: 'Carboy', capacity_liters: 23 }),
			],
		);
		const f = warnings.find((w) => w.code === 'fermenter_overflow');
		expect(f).toBeDefined();
		expect(f!.required).toBeCloseTo(25.2, 2);
	});

	test('no warning when at least one vessel in the category fits', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 9 },
			[
				gear({ type: 'all_in_one', name: 'G30', capacity_liters: 30 }),
				gear({ type: 'all_in_one', name: 'G70', capacity_liters: 70 }),
			],
		);
		expect(warnings).toEqual([]);
	});

	test('warns against the largest vessel when none fits', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 40, total_grain_kg: 16 },
			[
				gear({ type: 'all_in_one', name: 'G30', capacity_liters: 30 }),
				gear({ type: 'all_in_one', name: 'G40', capacity_liters: 40 }),
			],
		);
		const mash = warnings.find((w) => w.code === 'mash_overflow');
		expect(mash!.equipment_name).toBe('G40');
	});

	test('ignores inactive equipment', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 9 },
			[
				gear({ type: 'all_in_one', name: 'G30', capacity_liters: 30 }),
				gear({ type: 'all_in_one', name: 'G70 (sold)', capacity_liters: 70, is_active: false }),
			],
		);
		expect(codes(warnings)).toContain('mash_overflow');
	});

	test('silent when user owns no equipment in a category', () => {
		// Only a fermenter registered — mash/boil unknowable, fermenter fits.
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 9 },
			[gear({ type: 'fermenter', name: 'FermZilla', capacity_liters: 30 })],
		);
		expect(warnings).toEqual([]);
	});

	test('ignores vessels without capacity_liters for volume checks', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 9 },
			[gear({ type: 'all_in_one', name: 'Mystery rig' })],
		);
		expect(warnings).toEqual([]);
	});

	test('returns empty for extract recipes (no grain)', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 21, total_grain_kg: 0 },
			[gear({ type: 'all_in_one', name: 'G30', capacity_liters: 30 })],
		);
		expect(codes(warnings)).not.toContain('mash_overflow');
	});

	test('respects explicit boil_size_l over derived pre-boil', () => {
		const warnings = checkBrewability(
			{ batch_size_liters: 20, total_grain_kg: 5, boil_size_l: 33 },
			[gear({ type: 'kettle', name: 'Kettle 30', capacity_liters: 30 })],
		);
		const boil = warnings.find((w) => w.code === 'boil_overflow');
		expect(boil).toBeDefined();
		expect(boil!.required).toBeCloseTo(33, 2);
	});
});
