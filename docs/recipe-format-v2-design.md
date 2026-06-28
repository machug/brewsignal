# BrewSignal Recipe Format v2 — Design & Modern Technique Coverage

> Bead: tilt_ui-cnzl · Status: DRAFT (schema facts verified against BeerJSON source; technique figures cited — see §10 Sources)
> Goal: a comprehensive, transferable beer recipe JSON where **the software is never the bottleneck** — if a homebrewer has the ingredients, the model can capture the process used by modern hop-forward breweries (Fidens, Trillium, Other Half, Tree House, Monkish).

Verified 2026-06-27 by direct fetch of the BeerJSON master JSON Schemas + cited brewing-science sources. Remaining unverified items are tagged **VERIFY**.

---

## 1. Design principles & recommendation

1. **BeerJSON 1.0 is the spine.** The common subset must be readable by any BeerJSON tool — maximum transferability.
2. **One namespaced extension block** (`brewsignal`) for everything BeerJSON cannot express. We already have the mechanism (`format_extensions` per entity, `brewsignal_extensions` at root).
3. **Lossless round-trip with our DB** — v2 export must stop dropping richness the DB already holds (water, multi-culture, hop oils, extract hops). Today's `brewsignal_format.py` drops them: the primary defect.
4. **Units explicit** via BeerJSON `{value, unit}` objects.
5. **Process is first-class, not notes** — whirlpool temp, biotransformation dry hop, spunding are structured fields.

**RECOMMENDATION: additive-superset + single `brewsignal` namespace.** Use BeerJSON shapes wherever BeerJSON has a home (it covers far more than our v1 format exposes); put BrewSignal-only structures in a `brewsignal` block that degrades gracefully when stripped by a vanilla BeerJSON tool. Propose the genuinely-missing pieces (hop timing temperature, whirlpool use, water additions) upstream to BeerJSON.

---

## 2. Verified BeerJSON 1.0 coverage (what we ADOPT vs what we EXTEND)

Direct from the master schemas (github.com/beerjson/beerjson). This resolves the "core vs extension" question definitively.

### BeerJSON ALREADY covers (→ adopt; our DB is often behind)
| Capability | BeerJSON location / fields |
|---|---|
| Hop **oils** (full) | `OilContentType`: `total_oil_ml_per_100g, myrcene, humulene, caryophyllene, cohumulone, farnesene, geraniol, linalool, b_pinene, limonene, nerol, pinene, polyphenols, xanthohumol` |
| Hop core | `HopVarietyBase`: name, producer, product_id, origin, **year** (crop), form, alpha_acid, beta_acid; `HopAdditionType` = base + timing + amount |
| Dry-hop trigger by gravity | `TimingType.specific_gravity` (+ `time`, `step`, `duration`) |
| Cultures (rich) | `CultureBase.type` enum incl **ale, lager, brett, lacto, pedio, kveik, mixed-culture, spontaneous, malolactic, champagne, wine**; `alcohol_tolerance`, `attenuation_range`, `flocculation`, `max_reuse`, **`pof`**, **`glucoamylase`** (diastatic gene); `CultureAdditionType`: **`cell_count_billions`** (pitch), **`times_cultured`** (generation), timing, amount |
| Fermentation steps | `FermentationStepType`: name, start_temperature, end_temperature, step_time, **`free_rise`**, **`vessel`**, **`vessel_pressure`** (spunding), start/end gravity, start/end pH |
| Equipment | `EquipmentItemType`: `form` (HLT/Mash Tun/Lauter Tun/Brew Kettle/Fermenter/Aging Vessel/Packaging Vessel), `loss` (deadspace), `boil_rate_per_hour`, `grain_absorption_rate`, `maximum_volume`, weight, specific_heat, drain_rate_per_minute |
| Recipe vitals | `RecipeType`: original_gravity, final_gravity, alcohol_by_volume, **`ibu_estimate`** (carries IBU formula), color_estimate, efficiency (conversion + brewhouse), carbonation, **`beer_pH`**, **`apparent_attenuation`**, fermentation/boil/mash/packaging/ingredients/taste/style |
| Water **profiles** | `WaterBase`: calcium, magnesium, sodium, chloride, sulfate, bicarbonate, carbonate, **potassium, iron, nitrate, nitrite, fluoride**, pH (more ions than our model) |
| Fermentables | full maltster spec sheet (yield, moisture, diastatic_power, protein, etc.) |
| Misc | `MiscellaneousBase.type` enum: spice, fining, water agent, herb, flavor, **wood**, other |

### BeerJSON does NOT cover (→ `brewsignal` extension; genuine gaps)
| Gap | Why it matters | Fix |
|---|---|---|
| **Hop timing temperature** | `TimingType` has NO `temperature` → can't record whirlpool/hopstand/dry-hop temp (central to NEIPA) | `brewsignal.timing.temperature` |
| **Whirlpool / first-wort / dip-hop as `use`** | `UseType` enum = only `add_to_mash, add_to_boil, add_to_fermentation, add_to_package` — no whirlpool/first_wort/dip_hop | `brewsignal.hop_use` qualifier |
| **Water salt/acid ADDITIONS** | `WaterAdditionType` only has profile + `amount`; no gypsum/CaCl₂/epsom/acid dosing | `brewsignal.water_adjustments` (our `RecipeWaterAdjustment`, already in DB) |
| **Hop form cryo / T45** | `form` enum = extract/leaf/leaf(wet)/pellet/powder/plug — no cryo/LupuLN2/T45 | `brewsignal.hop_form` (map base form→`powder`/`extract`) |
| **Fruit additions** | misc enum has `wood` but **no `fruit`**; no sugar/Brix→gravity contribution anywhere | `brewsignal.fruit_additions` |
| **Wood/barrel detail** | only generic misc `wood`; no toast/char/previous-spirit/contact | `brewsignal.wood_additions` |
| **Dry-hop stage/purpose semantics** | multi-stage representable as N additions, but no stage index / purpose (aroma vs biotransformation) | `brewsignal` per-addition: `dry_hop_stage`, `purpose` |
| **Measurement/monitoring logs** | not in BeerJSON (out of its scope) | `brewsignal.measurements` on batch export |

---

## 3. Current BrewSignal coverage (the real baseline)

DB models (`backend/models.py`) are ~70% there; the **interchange format lags the DB**.

| Area | DB model | State |
|---|---|---|
| Water profiles | `RecipeWaterProfile` (source/target/sparge; Ca/Mg/Na/Cl/SO₄/HCO₃, pH, alkalinity) | ✅ richer than v1 format exposes; **add** BeerJSON's extra ions (K/Fe/NO₃/F) |
| Water adjustments | `RecipeWaterAdjustment` (8 salts + acid, mash/sparge/total) | ✅ ahead of BeerJSON; this IS the `brewsignal` extension |
| Hops | `RecipeHop` (timing JSON, extract fields, oils in `format_extensions`) | ⚠ move oils to BeerJSON `OilContentType`; add timing temp + dry-hop stage/purpose |
| Cultures | `RecipeCulture` (multi, attenuation range, flocculation) | ⚠ behind BeerJSON: add alcohol_tolerance, cell_count (pitch), times_cultured (generation), pof, glucoamylase, full type enum |
| Fermentation steps | `RecipeFermentationStep` (type/temp_c/time_days) | ⚠ behind: adopt start/end temp, vessel_pressure, free_rise, gravities |
| Equipment | — | ❌ none; adopt BeerJSON `EquipmentItemType` |
| Recipe vitals | og/fg/abv/ibu/color, target_* (imported vs calc) | ⚠ add ibu formula, apparent_attenuation, beer_pH, efficiency split |
| Fermentables | strong (coarse_fine_diff, moisture, diastatic_power, protein, max_in_batch) | ✅ |
| Fruit/wood/flavor | land in generic `RecipeMisc` | ❌ no domain fields → extension |
| Monitoring | `Reading`/`Batch` time series, calibration, actual_mash_ph | ✅ exists; surface in batch export |

---

## 4. Modern IPA / hazy technique → required data (cited)

Each technique → the structured fields needed → support. **Figures sourced (§10).**

### 4a. New England / hazy IPA
| Technique | Parameters (cited) | Data needed | Have? |
|---|---|---|---|
| Low-temp whirlpool / hopstand | ~80%+ of hops added at **170–180 °F (77–82 °C)** whirlpool [PrecisionFerm]; hopstand temp materially changes result [Brülosophy] | hop `use=whirlpool` + **temperature** + stand time + amount | ⚠ need timing.temperature ext |
| Heavy late/whirlpool load | — | amount (g) + derived g/L | ✅ |
| **Multi-stage dry hop** | splitting doses ↑ extraction efficiency of fruity compounds, ↓ polyphenols vs one big charge [Janish] | N additions + stage index + per-stage temp/time/amount | ⚠ stage/temp ext |
| **Biotransformation dry hop** | add during **active fermentation, ~day 1–3**; most biotransformation in the **first couple days**; geraniol→citronellol [Janish] | trigger = gravity/active-ferment (BeerJSON `timing.specific_gravity` ✅) + `purpose=biotransformation` | ⚠ purpose ext |
| Dry-hop **rate / saturation** | **~4–6 g/L** (Cascade) before diminishing returns; smaller doses extract more efficiently; absorption/beer-loss rises steeply (~6% at 1000 g/hL) [Janish] | amount + batch size → g/L | ✅ |
| **Cool/short dry hop** | **~58 °F (14 °C), as low as 40 °F (4 °C)**; ~**24 h** often sufficient (day-7 ≈ day-1); warmer ↑ polyphenols ~2× [Janish] | dry-hop temperature + contact time | ⚠ timing temp ext |
| Dip hopping (steep then to fermenter) | Japanese technique | `use=dip_hop` + temp | ⚠ ext |
| Soft, chloride-forward water | **chloride:sulfate ≥ 2:1** (~150–200 ppm Cl / 50–75 ppm SO₄), pros up to **3–3.5:1** [PrecisionFerm, HazyAndHoppy] | water target profile | ✅ |
| High-protein adjuncts | flaked oats/wheat, malted oats | fermentable type/grain_group | ✅ |
| **Hop creep** | hop amylases (α/β-amylase, **glucoamylase**, limit dextrinase) break dextrins → refermentation → **over-attenuation + diacetyl + over-carbonation/exploding bottles** [BA Tech Brief, BarthHaas, JIB] | model fermentables added post-hop; diacetyl-rest step; warning logic | ⚠ needs schedule + warning |
| Hop-creep mitigation | T45/extract over T90 (less plant matter); add hops at **~5 °P end of primary** so yeast clears diacetyl; **2–4 day warm diacetyl rest** [BarthHaas] | hop form; dry-hop timing vs gravity; ferment step temp profile | ⚠ partial |
| Yeast for haze/ester | London III / Conan / kveik | culture strain/form/temp | ✅ |
| LODO / closed transfer | O₂ ruins hazies | process flags (packaging O₂, closed transfer) | ❌ process metadata |

### 4b. West Coast IPA
Sulfate-forward water (raise CaSO₄; inverse of hazy) [Brülosophy sulfate:chloride]; bittering + whirlpool + dry hop; high attenuation/dryness. All supported except whirlpool temp + ibu formula.

---

## 5. Proposed v2 hop addition (BeerJSON core + `brewsignal`)

```jsonc
{
  "name": "Citra", "origin": "USA", "year": "2025",
  "form": "powder",                       // BeerJSON enum; real form in brewsignal
  "alpha_acid": { "value": 22, "unit": "%" },
  "beta_acid":  { "value": 4,  "unit": "%" },
  "amount":     { "value": 120, "unit": "g" },
  "oil_content": {                        // BeerJSON OilContentType (first-class!)
    "total_oil_ml_per_100g": 2.5, "myrcene": 55, "humulene": 12,
    "caryophyllene": 7, "farnesene": 1, "cohumulone": 22
  },
  "timing": {                             // BeerJSON TimingType (what it CAN express)
    "use": "add_to_fermentation",
    "time": { "value": 2, "unit": "day" },
    "duration": { "value": 1, "unit": "day" },
    "specific_gravity": { "value": 1.030 }   // biotransformation trigger
  },
  "brewsignal": {                         // extension: what BeerJSON can't
    "hop_form": "cryo",                   // cryo|t45|lupuln2 (base form maps to powder)
    "hop_use": "dry_hop",                 // whirlpool|first_wort|dip_hop|dry_hop|...
    "temperature": { "value": 18, "unit": "C" },  // whirlpool/dry-hop temp (NOT in BeerJSON timing)
    "dry_hop_stage": 1,
    "purpose": "biotransformation"        // aroma|bittering|flavor|biotransformation
  }
}
```
Multi-stage dry hop = N such additions; BeerJSON tools still read them as N dry-hop additions.

---

## 6. v2 additions checklist (build order)
1. **Catch interchange format up to DB** (water, multi-culture, extract hops) — stops data loss; no migration.
2. **Hop fidelity**: adopt `OilContentType`; add `brewsignal` temp/hop_form/hop_use/dry_hop_stage/purpose.
3. **Culture upgrade**: alcohol_tolerance, cell_count_billions, times_cultured, pof, glucoamylase, full type enum.
4. **Fermentation step upgrade**: start/end temp, vessel_pressure, free_rise, gravities (DB migration).
5. **Water**: extra ions; keep adjustments as `brewsignal.water_adjustments`.
6. **Equipment** object (BeerJSON `EquipmentItemType`).
7. **Fruit/wood/flavor** extensions (sugar contribution, toast/char/spirit).
8. **Recipe vitals**: ibu formula, apparent_attenuation, beer_pH, efficiency split, pre-boil gravity.
9. **Hop-creep warning** (derived from dry-hop rate + glucoamylase + no diacetyl rest).
10. **Batch measurement logs** in `brewsignal.measurements`.

---

## 6b. Brewfather reconciliation (3rd reference — de-facto homebrew app)

Existing repo research: `docs/BREWFATHER_FORMAT_ANALYSIS.md` (full reverse-engineered Brewfather JSON). Converters exist: `services/converters/brewfather_to_beerjson.py`, `recipe_to_brewfather.py`. Brewfather is the dominant homebrew tool, so v2's `brewsignal` block should **round-trip Brewfather** (import without loss, export back).

Brewfather captures things BeerJSON LOSES → must live in `brewsignal`:
| Brewfather feature | BeerJSON | Our DB | v2 home |
|---|---|---|---|
| Water per-stage **adjustments** (8 salts + **sodiumMetabisulfite/Campden** + acids array) | ❌ | ⚠ 8 salts+acid (no Campden) | `brewsignal.water_adjustments` (+ Campden) |
| Water **settings** (CaCl₂ dihydrate/anhydrous, per-salt mash/sparge/auto) | ❌ | ❌ | `brewsignal.water_settings` |
| Computed water metrics (RA, hardness, ionBalance, **SO₄:Cl ratio**, cations/anions) | ❌ | ❌ | derive or `brewsignal` |
| `mashPh`, `mashPhDistilled` | ❌ | actual_mash_ph (batch) | `brewsignal` |
| Hop `temp` (hopstand) + `day` (dry-hop day) + `timeUnit` | ❌ | timing JSON | `brewsignal` hop temp/stage (already planned) |
| **Nutrition** (calories alcohol/carbs/total, kJ; carbs g) | ❌ | ❌ | `brewsignal.nutrition` (derive) |
| **Inventory** per ingredient | ❌ | ❌ | `brewsignal.inventory` (optional) |
| **styleConformity** flags (og/fg/ibu/abv/color/carb in-range) | ❌ | ❌ | derive on read |
| `fgFormula`, `ibuFormula` | ibu method ✅ | ❌ | recipe vitals |
| Equipment: boilOffPerHr, trubChillerLoss, mashTunDeadSpace, grainAbsorptionRate, hopstandTemperature, hopUtilization | partial | ❌ | adopt BeerJSON `EquipmentItemType` + `brewsignal` hop utilization |

**Implication for structure:** the single `brewsignal` block mirrors Brewfather's proven groupings (`water_adjustments`, `water_settings`, `nutrition`, `inventory`) so Brewfather↔BrewSignal is near-lossless and BeerJSON tools still read the core.

---

## 7. Decisions — LOCKED (2026-06-27)
1. **Structure**: BeerJSON 1.0 field shapes for the core + **single namespaced `brewsignal` block** for all extras; modeled to round-trip Brewfather. Stripping `brewsignal` leaves valid BeerJSON.
2. **Versioning**: **breaking `brewsignal_version: "2.0"`** + a v1→v2 upgrader and v2→BeerJSON/BeerXML/Brewfather exporters. v1 importer retired once the upgrader covers it.
3. **First build slice**: **format catch-up only** — stop the interchange format/serializer dropping DB richness (water, multi-culture, extract hops); regenerate the schema doc from the Pydantic model. No DB migrations yet.
4. **Fruit/sugar contribution**: **store measured** (amount + Brix/sugar%) and **derive** gravity/ABV.

Deferred to later slices: hop fidelity ext, culture/fermentation/equipment DB migrations, fruit/wood tables, hop-creep warning, measurement logs.

---

## 8. What's still VERIFY
- Exact `IBUEstimateType` method enum values (tinseth/rager/garetz) and `ColorType` method.
- Brewfather export JSON structure (their water-tool fields) — for import + UX parity.
- BeerXML 1.0 precise gaps for the exporter.
- Dip-hopping temperature specifics.

---

## 9. Bottom line
We're closer than it looks: **BeerJSON covers most "advanced" things our v1 format omitted** (oils, cultures, equipment, pressure fermentation, attenuation/beer-pH). The job is (a) stop the interchange format lagging the DB, (b) upgrade a few DB tables to BeerJSON parity, and (c) add a small, well-scoped `brewsignal` extension for the handful of genuine gaps that block modern NEIPA capture — **hop timing temperature, whirlpool/dip-hop use, water salt/acid additions, hop form (cryo/T45), fruit, wood/barrel, and dry-hop stage/purpose**. That set is exactly what lets a homebrewer reproduce a Fidens-style beer in the data model.

---

## 10. Sources
- BeerJSON master schemas (verified field-by-field): https://github.com/beerjson/beerjson · docs https://beerjson.github.io/beerjson/ — timing.json, hop.json, water.json, fermentation_step.json, equipment.json, recipe.json, misc.json, culture.json
- Scott Janish — *What We Know About Dry Hopping* (rate/saturation, cool & short, biotransformation): https://scottjanish.com/what-we-know-about-dry-hopping/
- Scott Janish — *A Case for Short And Cool Dry Hopping*: https://scottjanish.com/a-case-for-short-and-cool-dry-hopping/
- Precision Fermentation — *Water Chemistry for Hype Beer Styles* (whirlpool 170–180 °F, chloride:sulfate): https://www.precisionfermentation.com/blog/water-chemistry-for-hype-beer-styles/
- Hazy and Hoppy — *Water Treatment for New England IPAs* (Cl:SO₄ 2:1→3.5:1): https://hazyandhoppy.com/water-treatment-for-new-england-ipas/
- Brülosophy — *Sulfate:Chloride Ratio* (WCIPA vs hazy): https://brulosophy.com/2016/10/03/water-chemistry-pt-6-sulfate-to-chloride-ratio-exbeeriment-results/
- Brülosophy — *Hop Stand Temperature 185 vs 203 °F*: https://brulosophy.com/2022/10/17/exbeeriment-impact-hop-stand-temperature-has-on-a-hazy-ipa/
- Brewers Association — *Hop Creep Technical Brief*: https://cdn.brewersassociation.org/wp-content/uploads/2020/05/Hop-Creep-%E2%80%93-Technical-Brief.pdf
- BarthHaas — *Hop Creep: what is it and how do I avoid it* (mechanism + mitigation, T45/extract, 5 °P timing, diacetyl rest): https://www.barthhaas.com/ressources/blog/blog-article/hop-creep-what-is-it-and-how-do-i-avoid-it-in-the-brewery
- Journal of the Institute of Brewing — *Contribution of β-amylase from hops to fermentability of dry hopped beer*: https://jib.cibd.org.uk/index.php/jib/article/view/75
