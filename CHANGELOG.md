# Changelog

All notable changes to BrewSignal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Readable batch and recipe addresses** (tilt_ui-9hg) - Batches and recipes now open at addresses like `/batches/16-american-pale-ale` and `/recipes/25-west-coast-ipa`. The number at the front is what counts, so old links such as `/batches/16` still work, open the right page and switch to the readable form. Renaming a batch or recipe never breaks a link.

### Removed
- **Unused MPC temperature controller** (tilt_ui-29im) - `backend/ml/control/mpc.py` was never switched on and, in simulation, held the beer in band less often and switched far more than the hysteresis controller. The code, its config and its tests are gone. Temperature control is unchanged.

### Fixed
- **Dry hops show "In fermenter" instead of a negative time** (tilt_ui-8vd) - Imported dry hops with no day set (stored as -1) showed as a negative time in the recipe hop schedule.
- **Control status shows Celsius** (tilt_ui-xrq5.6) - The global target and hysteresis were still stored in Fahrenheit (66.2 and 1.08 on the Pi), because the old Fahrenheit-to-Celsius migration missed them. They are converted on startup, and the defaults are now 20 C and 0.5 C.
- **Predictions no longer vanish near the end of a batch** (tilt_ui-fod1) - The FG prediction was limited to 0.003 below the recipe FG, and its starting guess was the latest reading. When a beer fermented drier than the recipe (most do), the guess fell outside the limit and the fit failed, so predictions disappeared just when they mattered. The limit is now 0.015 below the recipe FG (floor 0.990) and the guess is kept inside it.
- **ML state no longer leaks between batches** (tilt_ui-89af) - When a hydrometer moved to a new batch, its smoothing filter and history carried over from the old batch, so filtered gravity and predictions started from the previous beer. Each device's ML state now belongs to one batch and starts fresh for a new one. The filter also starts from the first real reading instead of a default (it used to show a filtered temperature far too high for hours after a restart). Completed batches show their own predictions instead of the device's live ones.

## [2.14.0] - 2026-11-12

### Added
- **Memory page** (tilt_ui-or48) - New Memory page (System > AI > Manage memory) lists everything the assistant remembers: your saved learnings and facts it picked up from chats. Delete one item, or delete all. New `GET /api/memory`, `DELETE /api/memory/{id}`, `DELETE /api/memory`. Memory text is sent to OpenAI's embedding model (via OpenRouter) to find related memories.
- **New logo and app icons** (tilt_ui-nv1r.7) - New "Tilt Meniscus" mark (a tilted hydrometer at the wort surface) in the top bar, favicon, apple-touch icon, 512px icon and web manifest. The old hop-cone icon and logo are gone. The sign-in page now renders without the app chrome.
- **Automatic recipe scaling** - New `POST /api/recipes/{id}/scale`. Pick a vessel preset (Grainfather, BrewZilla, Braumeister, corny keg) or type a size, and every per-batch amount scales to match: fermentables, hops, miscs, yeast, mash infusions, water volumes and salts (ppm kept constant), boil size and priming sugar. Stats are recalculated. A preview shows current and scaled amounts before you save over the recipe. Large jumps are handed to the AI reviewer.
- **Equipment-aware brewability warnings** - The recipe page checks mash volume, grain weight, pre-boil volume and batch size (with 20% headspace) against the largest vessel of each type in your Equipment inventory. Vessel types you have not registered stay silent.
- **BrewSignal Recipe Format v2 export and import** (tilt_ui-0jkg, tilt_ui-4bwa, tilt_ui-cnzl) - New `/export/brewsignal` and `/export/beerjson` endpoints. v2 is BeerJSON 1.0 plus one `brewsignal` extension block, and it round-trips Brewfather data. v2 documents can be imported. Brewfather export now includes water profiles and adjustments. v1 and v2 schemas are generated from the models. The design is written up in `docs/recipe-format-v2-design.md`.
- **Hop extract support** (tilt_ui-0l5, tilt_ui-m4y) - Recipes can hold hop extracts (for example Abstrax products) measured in ml. The hop picker has an extract mode that switches units and limits timing to the cold side. Extracts add no IBU. Boil-side extracts are rejected. Extracts survive save, reload, review and export.
- **Bulk hop inventory update from the assistant** (tilt_ui-86wt) - Paste a list of hop names and grams into the assistant. It matches names against the hop library (typos like "Galaxxy" resolve to Galaxy), shows a preview card, and updates inventory only after you confirm. Crop year, storage and notes are kept. New `POST /api/inventory/hops/bulk` with dry-run and apply modes.
- **Assistant status line** (tilt_ui-jx3p) - While the assistant works, the chat shows "Reading your question...", "Using tool: ..." or "Thinking..." next to the busy dots.
- **Assistant can edit recipes in place** - New `update_recipe` tool. Before, an edit request created a duplicate recipe. The assistant also offers to apply fixes after a low style-fit review, and exposes the recipe review as a `review_recipe` tool. Saving or updating a recipe needs your confirmation in the conversation.
- **Kalman-filtered temperature and gravity on the chart** (tilt_ui-96m) - Filtered SG and filtered temperature show as separate dashed series with legend toggles. The legend hides them when no filtered data exists.
- **Heating and cooling bands on the chart** (tilt_ui-wims) - Control events are drawn as translucent red (heating) and blue (cooling) bands, with a Heat/Cool legend toggle.
- **API reference at `/scalar`** (tilt_ui-zilo) - Interactive Scalar API docs next to the existing Swagger `/docs`.
- **AI Review on the recipe view page** - The AI Review button and modal were only on the edit page. The modal no longer closes when a text selection ends on the overlay.
- **Add First Reflection works** - The button on the completed-batch tab opens a form with a phase selector and four fields: what went well, what went wrong, lessons learned and next-time changes.
- **BJCP style on the recipe header** (tilt_ui-6b9) - The beer header stats card shows the BJCP style. Common brewer names (West Coast IPA, NEIPA, XPA, DIPA, Dry Stout) resolve to the right BJCP style. A one-time migration fills in the missing style on older recipes. The strict match never guesses from name or notes.
- **Other Ingredients table** (tilt_ui-ifl6) - Non-water miscs now show on the recipe detail page.
- **Deploy script** - `deploy/deploy.sh` runs the Pi deploy in one command: fetch, reset, frontend build when needed, restart, health check.

### Removed
- **Old assistant chat stack** (tilt_ui-qzk0.3) - The AG-UI router (`/api/ag-ui/*`), its browser client and its tests are gone. Thread headers and old messages stay in their tables. The model-context pruning helper that only the old loop used is removed too.

### Changed
- **LiteLLM removed** (tilt_ui-i5nw) - Recipe review, the assistant status and test endpoints and the memory feature now call the model through Pydantic AI and the OpenAI-compatible API, using the same AI settings as the chat. The Pi install is smaller (about 15 fewer packages). The `litellm_available` status field stays and always reads true. Anthropic as a direct provider is not supported by any assistant feature; use OpenRouter for Claude models.
- **Guided tasting on the new assistant** (tilt_ui-qzk0.3) - The tasting panel on the batch page now talks to the same chat as the assistant page. It looks and works the same, and each session also appears in the assistant's chat list.
- **Assistant chat rebuilt** (tilt_ui-qzk0) - The assistant now runs on Pydantic AI and the Vercel AI SDK instead of a hand-built chat loop.
  - The server keeps the chat history. The browser sends only the new message, so a client cannot fake a tool result or an approval.
  - Hop stock changes show one card that goes from Proposed to Applied. An approval only works once, and only for the change the assistant actually proposed.
  - New chat page in the Clean Instrument style: chat list in a slide-over drawer, one activity row per answer (raw tool data behind a toggle), and a compact composer with Send and Stop.
  - Existing chats are copied to the new store and still open. The assistant's past-chat search covers new chats too.
  - A finished hop update is saved even if the reply after it fails or the page is closed. Two tabs cannot run the same chat at once.
- **Clean Instrument UI redesign** (tilt_ui-nv1r, tilt_ui-bf4p) - New design system and app shell across the whole app. Direction chosen from four mockups.
  - Foundation: new colour and type tokens, brand fonts loaded by link, new top bar and phone "More" menu.
  - Home: new layout. Chart gravity ticks no longer repeat, and the chart hides its stats on Home (tilt_ui-nv1r.2).
  - Batches: list and detail screens restyled (tilt_ui-nv1r.3).
  - Recipes: list and detail restyled. The phone layout gets a More menu, a two-column stat grid and no clipped tables (tilt_ui-nv1r.4).
  - Recipe builder (new, edit, import): sticky side rail, grid rows for hops and fermentables, inline units. Pickers close with Escape and return focus (tilt_ui-nv1r.4).
  - Inventory, Library, Knowledge and Yeast restyled (tilt_ui-nv1r.5).
  - System, Devices, Calibration, Logging and Login restyled, with sub-page navigation state, breadcrumbs and aligned ledgers (tilt_ui-nv1r.6).
  - Light and dark theme toggle. Light theme form-control borders meet 3:1 contrast, and accent and warning text meet 4.5:1 on subtle fills.
- **Hop stand IBU depends on temperature** - Brewfather and BeerXML "Aroma" hops now import as whirlpool and keep the stand temperature. Whirlpool IBU uses the existing stand-time ramp times a temperature factor (0.23 at 80 C, 0.50 at 90 C). Whirlpool hops with no temperature behave as before. Hop stands export to Brewfather as "Aroma". The editor keeps stand temperature and short hop uses on export.
- **Backend IBU matches the frontend** (tilt_ui-nbh0) - Pellet and first-wort hops get the +10% utilisation in the backend calculator too.
- **Sugars and extracts use full potential** (tilt_ui-ju0z) - Brewhouse efficiency no longer applies to them.
- **Water volumes match Brewfather** (tilt_ui-4pzy) - Mash ratio, grain absorption, mash-tun deadspace and boil-off defaults were recalibrated against a real Brewfather export. Total volume stays equal to mash plus sparge when sparge clamps to zero.
- **Dry hop durations show in days** - The Hop Schedule shows editor-saved dry hop durations in days. The BU:GU balance label is shared, and "Very Bitter" starts at 1.0.
- **Water additions panel** (tilt_ui-r1ya) - Clearer treated-volume labels, empty stages hidden, lime and MgCl2 shown.
- **Assistant model list** (tilt_ui-e2xg) - The OpenRouter model dropdown uses the live catalogue, and default models resolve against it.
- **Assistant recipe saves** - The assistant saves first and offers a review after, instead of reviewing before it saves. Tool descriptions and prompts were aligned with this flow.
- **Recipes sync to cloud with fewer failures** - Recipe hop sync lands on the cloud database and reports failures (tilt_ui-nyn). Cloud user ids use the Postgres uuid type (tilt_ui-unt). Column drift is fixed on boot (tilt_ui-xf8). The healthcheck timeout is longer so a cold boot passes (tilt_ui-7ba).
- **Faster startup** (tilt_ui-h0j) - Recipe backfills run after boot instead of blocking it.

### Fixed
- **Stall alert no longer fires in the lag phase** (tilt_ui-zbhm) - The old rule alerted whenever gravity was flat and progress was under 90%, which included the first hours of every batch. A stall now means the gravity fell less than 0.6 points/day over the last 12 hours, after it has already dropped at least 4 points from OG, while still more than 4 points above the expected FG. Without a recipe FG the alert is info only. The anomaly detector's old "stuck" and "unusual increase" rules (which flagged most normal readings) are replaced by a step-change rule: six readings in a row more than 1 point off the recent trend, flagged once (dry hop, or hydrometer lifted or moved). It works at any reporting interval up to 1 hour, does not raise a false reverse alert after a shift, and the alert stays until you dismiss it. After a restart the app refills the 12-hour window from saved readings, so the stall check is not blind for 12 hours. Hydrometers that send over HTTP (iSpindel, GravityMon) had the same alert crash that tilt_ui-xrq5.5 fixed for Tilt; both paths now share one alert-context helper.
- **Fermentation alerts work again** (tilt_ui-xrq5.5) - Alert detection crashed on every check because it read recipe fields that no longer exist (yeast, OG/FG on the batch), so no fermentation alert could fire. It now uses the recipe's yeast culture temperature range and the measured or recipe OG.
- **Temperature control safety** (tilt_ui-f50x, tilt_ui-xrq5.1) - If the wort reading is more than 15 minutes old, the heater and cooler both switch off and an alert is raised. The heater is limited to 4 hours on, then a 30-minute lockout. The cooler is not limited by time alone, because a cold crash legitimately runs it for days: it is switched off (same lockout, with an alert) only if it has been on for 6 hours without the wort cooling by at least 0.5 C, which usually means the sensor is not in the beer, or after 72 hours as an absolute backstop (tilt_ui-xrq5.4). The 5-minute minimum between switches now survives restarts. A device only turns on after the other is confirmed off, including manual overrides and the manual heater button.
- **One set of equipment per active batch** (tilt_ui-8d49) - Two fermenting or conditioning batches can no longer share a heater, cooler or hydrometer. Saving such a batch shows an error, and if a conflict still exists the controller turns the shared equipment off and raises an alert naming both batches.
- **Batch cooler saved on create, 0.0 C readings** (tilt_ui-xrq5.2, tilt_ui-xrq5.3) - Creating a batch now keeps its cooler switch, and a wort reading of exactly 0.0 C is no longer treated as missing.
- **Readings are kept permanently** (tilt_ui-ktk7) - The Pi deleted hydrometer readings older than 30 days every hour, and the System page had a button that did the same. Both are gone, so past fermentations stay available for predictions and the assistant. Readings of batches you delete can still be cleaned up from Maintenance.
- **CSV export works again** (tilt_ui-ktk7) - The Logging page's Download CSV used a removed table name and failed.
- **Hosted memory is durable and per-user** (tilt_ui-or48) - On the hosted version the memory index lived in a temp folder that was wiped on every deploy. It now lives in the Supabase Postgres (pgvector), with each user's memories filtered by user id and locked by Row Level Security. Deleting a user in Supabase Auth deletes their memories. Run migration `20261111000000_hosted_memory_pgvector.sql`; saved learnings are re-indexed on the next start. The Pi keeps its local index. Deleting a memory checks the owner, and if the memory store fails the delete returns an error and keeps your saved learning so you can retry.
- **Local Lite LLM switch saves** (tilt_ui-fbk8) - The System page switch for title summaries on the Pi's AI HAT was dropped by the server and never took effect. It now saves, and a test fails if any System setting is dropped again.
- **Assistant memory recall works** (tilt_ui-scbr) - Memory (mem0) was never installed, so the assistant could save learnings but never recall them. It is now a dependency. Saved learnings are indexed on start, and old learnings are added once in the background. Embeddings go through OpenRouter (`openai/text-embedding-3-small`). Memory extraction uses the cheap fast model, skips short turns, and never runs twice for one turn. Set `ai_memory_auto_extract` to false to turn off automatic extraction. If memory search fails, the assistant falls back to a keyword search of your saved learnings.
- **Legacy chat titles** (tilt_ui-qzk0.4) - Old chats titled with a fragment of message text (markdown, table pipes, line breaks, over 60 characters) are re-titled in the background after startup. Renamed chats are left alone. Without a model, the title is a cleaned start of your first message. New chats get a clean first-message title instead of raw text.
- **Calibration** (tilt_ui-nv1r.6.1, tilt_ui-y5nm) - The API accepts empty and single-point calibration lists, so the first add, remove and clear work. A single point is stored but only applied with two or more points.
- **Inventory hop names** (tilt_ui-vket) - Hop name matching ignores accents.
- **Assistant chat** - Markdown tables render (tilt_ui-mizm). The busy indicator stays on for the whole run (tilt_ui-4acv). Replies are no longer empty when model reasoning uses up max_tokens (tilt_ui-atvb). Restoring a thread brings back a pending hop inventory card (tilt_ui-86wt). Thread titles no longer cut off mid-sentence. The memory service uses OpenRouter correctly. The review tool no longer fails on an uninitialised LLM service.
- **AI review modal** (tilt_ui-6h2c) - Shows the BJCP style, not the recipe type. Reviews use the stats the card displays, not `target_*` (set from import).
- **Brewability warnings** - Fixed false negatives. Warnings read grain total from the editor data, leave out kettle additions, fetch the full equipment page, and treat zero or negative capacities as unknown.
- **Brewfather import and export** (tilt_ui-zlzz, tilt_ui-mjdc, tilt_ui-mrn) - Duplicate water-adjustment miscs are skipped when a water block exists. Misc amounts show in their true unit. Importing a multi-yeast recipe warns that extra cultures are dropped in v1 conversion.
- **v2 format hardening** (tilt_ui-4bwa) - Strict BeerJSON placeholders for bare recipes, safe download filenames, per-item format extensions kept on export, and explicit step types preferred on import. Duplicate hop extras merge and bad water entries are named in errors. Acids given only as a concentration survive export, and empty water profiles are skipped. The style link is applied on import. Exports of another user's recipe are denied, and the loss of `created_at` is documented.
- **SRM for dark grains** - Missing grain colours come from the fermentable reference table, so a stout with roasted barley no longer shows about 4 SRM. The editor backfills grain colour from stored rows.
- **Recipe saves** - UI ingredients are written to the relationship tables, not only to the editor cache. The edit form saves the BJCP style, not just free text in `type`. BeerXML and Brewfather import resolve the BJCP style.
- **Imported hop stands** - A migration moves old zero-minute boil hops to whirlpool, once and only when the duration is explicitly zero (the local database also retags a missing duration). Supabase has a matching backfill.
- **Recipe page stats** - Stats are computed live to match the editor and the 2.13.0 IBU model. Stored SRM is kept when fermentables lack colour. Empty fermentable or hop lists are respected.
- **Recipe review** - Reviews use edited ingredients and ignore stale imported targets. Stored dry hop duration is kept. The watcher skips its first run.
- **Dry hops** - Boil time is zero on dry hops, and the IBU calculator handles BeerJSON use forms in saved recipes.
- **Fermentation prediction** - The curve fit uses calibrated SG, not Kalman-filtered SG. Early filtered values sat far below real readings, so predictions stayed on "Waiting for fermentation to progress".
- **Mobile recipe page** - The action row wraps below 640px, so Brew This and Delete are no longer clipped.
- **Pi deploy** (tilt_ui-l842) - Backend dependencies sync when the dependency manifest changes.
- **Build lockfile** (tilt_ui-rnf) - `uv.lock` matches the current version.

## [2.13.0] - 2026-04-25

### Fixed
- **Imported recipe stats no longer clobbered on save** (tilt_ui-5no) - PUT `/api/recipes/{id}` recalculation is now opt-in via `?recalculate=true`. Default false preserves brewer-declared OG/FG/ABV/IBU/SRM from imported recipes. Recipe edit form no longer auto-recalculates; a separate explicit action calls the existing `POST /api/recipes/{id}/recalculate` endpoint when refresh is wanted.
- **Brewfather Whirlpool hops produce real IBU** (tilt_ui-53n, tilt_ui-23u) - Converter now maps Whirlpool to `add_to_whirlpool` instead of collapsing into `add_to_boil` with 0-min duration. New stand-time IBU model in backend, frontend, and LLM-tools calculators uses linear ramp `min(0.05 + 0.005 * stand_min, 0.20)` — 5% utilization at flameout, 20% cap at 30-min stand. Reverse converter and frontend HopUse normalization extended; HopSelector renders a "Stand" input for whirlpool hops and resets duration sensibly on use changes.
- **Brewfather pre-boil volume preserved** (tilt_ui-u19) - Converter maps `boilSize` to BeerJSON `boil.boil_size`. Previously dropped on import, leaving `boil_size_l` NULL in the database.
- **Brewfather water adjustments preserved** (tilt_ui-2br) - Mash and sparge volumes plus salt additions (gypsum, calcium chloride, etc.) and acid additions now persisted into `recipe_water_adjustments`. Attachment of the raw Brewfather water object as `_brewfather_water` moved into the converter so any caller (importer, future LLM tooling) gets it automatically.
- **Fermentation step types** (tilt_ui-psa) - Step type inference now recognises diacetyl rest and cold crash patterns. Previously every step name that didn't contain `primary` / `secondary` / `conditioning` collapsed to `primary`, losing process intent in the fermentation phase UI and temp control.
- **Dry-hop IBU contribution audited** (tilt_ui-4te) - Confirmed all three IBU calculators (backend `services/brewing.py`, LLM `services/llm/tools/recipe.py`, frontend `lib/brewing/calculations.ts`) correctly skip dry-hop additions. Pinned with regression tests covering long-form `add_to_fermentation`, short-form `dry_hop`, and mixed boil + whirlpool + dry-hop combinations.
- **Repeated `save_brewing_learning` on Thread Resume** - Assistant no longer re-saves the same brewing insights every time a conversation is resumed
  - Root cause: tool call history was stripped during thread reload, so the LLM couldn't see its prior tool invocations
  - Now persists assistant tool calls and tool result messages to the database
  - Full message history (user, assistant with tool_calls, tool results) restored on resume
  - Existing DB-level duplicate guard (>50% word overlap) serves as safety net

### Added
- **Imported brewer-declared stats stored separately** (tilt_ui-ak6) - New `target_og`, `target_fg`, `target_abv`, `target_ibu`, `target_srm` columns on `recipes`. Importers populate both target_* and canonical og/fg/abv/ibu/color_srm; the recalculator only writes the canonical fields, leaving target_* as the imported source-of-truth. Recipe detail UI shows a small "src N" hint under each stat when the imported target meaningfully differs from the calculated value (thresholds: OG/FG 0.002, ABV 0.2%, IBU 3, SRM 1). Migration backfills target_* from existing canonical values on upgrade. Sync to Supabase carries the new columns through.
- **Native BrewSignal recipe import** (tilt_ui-kew) - `POST /api/recipes/import` now accepts native BrewSignal JSON files (`.brewsignal` extension). Auto-detection routes BrewSignal-shaped payloads through Pydantic validation against `BrewSignalRecipe`, then through a new `BrewSignalToBeerJSONConverter` that funnels into the same serializer + persist path as other formats. Detection fingerprints on `_format` / `brewsignal_version` markers, `recipe` envelope wrapper, BrewSignal-only snake_case keys (`batch_size_liters`, `color_srm`, `boil_time_minutes`, etc.), nested ingredient shape (`amount_kg`, `amount_grams`, `alpha_acid_percent`), and a singular `yeast` dict. Brewfather camelCase markers (`_type`, `batchSize`, `boilTime`, scalar `efficiency` / `carbonation`, ingredient `amount` / `alpha`) keep routing to brewfather. Explicit override available via `?source_format=brewsignal`.
- **`?recalculate=true` query param** on `PUT /api/recipes/{id}` for explicit stat refresh (see Fixed above).
- **Context Window Management** - Prevents hard failures on long conversations
  - Token counting using litellm's tokenizer (includes tool definitions in budget)
  - Pre-flight context check before entering agent loop
  - Per-iteration guard with sliding-window pruning when context exceeds budget
  - Graceful "context limit reached" message instead of silent API failure
  - `contextUsage` emitted via STATE_DELTA for frontend visibility

### Migration
- New SQLite migration `add_recipe_target_stats` adds and backfills target_* columns idempotently.
- New Supabase migration `20260425124000_recipe_target_stats.sql` mirrors the change for cloud deployments. Apply via `supabase db push` or Supabase dashboard before deploying the backend.

## [2.12.0] - 2026-03-02

### Fixed
- **Yeast Override Clear Button** - Fixed clear selection button not working on batch edit page
  - The `$effect` that initializes yeast from batch data was re-running on every clear, immediately re-setting the value
  - Added initialization guard so it only runs once on page load
- **Anomaly Reasons Not Stored** - Fixed anomaly detection reasons never being saved to database
  - Key mismatch: detector returned `reason` (singular) but pipeline manager read `reasons` (plural)
  - Existing anomalies showed "Unknown reason" because the field was always null
  - New anomalies now correctly store reasons like `unusual_increase` or `stuck_fermentation`
- **Anomaly Markers Not Rendering on Chart** - Fixed uPlot series config that suppressed point rendering
  - `paths: () => null` was preventing all rendering including points
  - Replaced with `stroke: transparent` and `width: 0` for proper points-only rendering
  - Added `space: 0` to ensure sparse anomaly points are not skipped

### Changed
- **Merged Lifecycle Stepper into Phase Tabs** - Removed redundant stepper row above tab bar
  - Tabs now show green checkmarks for completed phases and a pulsing blue dot for current phase
  - Saves vertical space on batch detail page
- **Compact Recipe Targets** - Replaced full card with single inline strip
  - Shows OG, FG, ABV, yeast, and recipe name in one row with dividers
  - Saves significant vertical space on all phase views
- **Balanced Fermentation Layout** - Moved notes card to left column under recipe strip
  - Eliminates large empty space next to temperature control and sidebar cards
- **Compact Temperature Control** - Heater/cooler status now uses inline chips instead of stacked cards
  - Side-by-side chips: `🔥 Heater OFF | ❄️ Cooler ON`
  - Entity IDs available on hover as tooltips

### Added
- **Anomaly Details Strip** - New section below chart showing detected anomalies
  - Displays timestamp, gravity value, and reason for each anomaly
  - Toggles visibility with the existing anomaly legend button

## [2.11.0] - 2026-01-25

### Added
- **Brew Day Chilling Status** - Real-time chilling progress during brew day phase
  - Progress bars showing current vs target temperature
  - "Ready to Pitch!" indicator when target reached
  - Chilling mode now works during both "planning" and "brewing" status
- **Cross-Device Timer Sync** - Brew day timer persists to database for multi-device access
- **Collapsible Brew Day Checklist** - Compact, expandable checklist UI
- **Brewfather JSON Export** - Export recipes in Brewfather-compatible format
- **BeerJSON Yeast Migration** - Auto-populates `recipe_cultures` from legacy yeast fields
- **Yeast Auto-Matching** - Batch creation auto-links yeast strain from recipe name

### Fixed
- ML predictions card no longer stuck on "Loading..." for new batches with insufficient data
- Removed duplicate chilling banner during brew day (consolidated into phase card)
- Brew day observations (mash temp, pre-boil gravity, efficiency, notes) now persist correctly
- Recipe yeast fields included in API responses for RecipeBuilder display
- Yeast selector limit and hop form defaults fixed
- "Brewing" status batches now appear in active batches list
- Equipment object added for Brewfather import compatibility
- Assistant now sees yeast info via fallback to recipe fields when batch.yeast_strain unavailable

### Technical
- Refactored `tools.py` (3326 lines) into modular `tools/` package with 7 focused modules:
  - `__init__.py` - TOOL_DEFINITIONS and execute_tool dispatcher
  - `yeast_style.py` - Yeast strain and style search tools
  - `inventory.py` - Hop/yeast inventory and equipment tools
  - `ingredients.py` - Hop variety and fermentable reference tools
  - `fermentation.py` - Batch monitoring and fermentation history
  - `recipe.py` - BeerJSON normalization and brewing calculations
  - `utility.py` - Datetime, URL fetch, chat management tools

## [2.10.0] - 2026-01-23

### Added
- **MQTT Publishing for Home Assistant** - Publish fermentation data to Home Assistant via MQTT auto-discovery
  - Automatic sensor creation when batches start fermenting
  - Sensors: gravity, temperature, ABV, status, days fermenting
  - Binary sensors: heater active, cooler active
  - Device grouping: All sensors for a batch grouped under single HA device
  - Auto-cleanup: Entities removed when batch completes or is deleted
  - Fire-and-forget publishing: MQTT failures don't block reading storage
  - Compatible with voice assistants (Alexa, Google Home, Siri) via Home Assistant
- **MQTT Configuration UI** - New System settings section for MQTT broker configuration
  - Enable/disable toggle
  - Broker host, port, username, password fields
  - Configurable topic prefix (default: `brewsignal`)
  - Test connection button with status feedback
  - Home Assistant setup instructions
- **MQTT Status API** - New endpoints for MQTT monitoring
  - `GET /api/mqtt/status` - Check MQTT connection status and configuration
  - `POST /api/mqtt/test` - Test MQTT broker connection
- **AI Assistant Memory** - Cross-thread conversation search and recall
  - New `search_threads` tool allows the assistant to search previous conversations
  - Searches thread titles and message content with context snippets
  - Enables recalling recipes, discussions, and brewing info from past chats
- **AI Assistant Chat Management** - Enhanced conversation control
  - New `rename_chat` tool allows the assistant to rename conversation threads
  - Title locking prevents auto-summarization from overwriting manually set titles
  - Dynamic sidebar updates when threads are renamed (real-time via STATE_DELTA)
- **AI Assistant Web Access** - New `fetch_url` tool for retrieving web content
  - Assistant can fetch and read content from URLs
  - Useful for looking up brewing resources, recipes, and documentation

### Fixed
- **New Chat Thread Creation** - Fixed bug where starting a new chat reused old thread ID
  - `useAgent.clear()` now properly resets `currentThreadId`
  - New threads immediately appear in sidebar after first message
  - Thread list auto-refreshes on conversation completion

### Technical
- New `backend/services/mqtt_client.py` - MQTT client service with aiomqtt
- New `backend/mqtt_manager.py` - Background connection manager with auto-reconnect
- New `backend/routers/mqtt.py` - MQTT status and test endpoints
- MQTT discovery publishes to `homeassistant/sensor/brewsignal_{batch_id}_*/config`
- State updates publish to `brewsignal/batch/{batch_id}/*` topics
- Added `aiomqtt>=2.0.0` dependency

## [2.9.0] - 2026-01-17

### Added
- **Unified Library Page** - Consolidated reference data into single `/library` page
  - Tabbed interface for Yeast, Hops, and Fermentables
  - Search and filter across all ingredient types
  - Renamed "Yeast" nav link to "Library"
- **Hop Varieties Reference Database** - 200+ hop varieties from Beer Maverick
  - Search by name, purpose (bittering/aroma/dual), origin, alpha acid range
  - Detailed profiles with aroma descriptors and substitutes
  - New `search_hop_varieties` AI assistant tool
- **Fermentables Reference Database** - Grain, sugar, and extract library
  - Search by name, type, maltster, color range, diastatic power
  - Covers base malts, specialty malts, sugars, extracts
  - New `search_fermentables` AI assistant tool
- **Prompty Template System** - Externalized AI prompts using Microsoft Prompty standard
  - `assistant.prompty` - Main brewing assistant system prompt
  - `title.prompty` - Conversation title generation
  - Template variables for batch size, efficiency, equipment
- **Inventory Management System** - Track brewing equipment, hops, and yeast inventory
  - **Equipment Tracking** - Manage kettles, fermenters, mash tuns, and all-in-one systems (Grainfather, etc.)
    - Track capacity (liters/kg), brand, model, and active status
    - Support for equipment types: kettle, fermenter, mash_tun, hot_liquor_tank, cooler, pump, chiller, kegging, all_in_one, other
  - **Hop Inventory** - Track hop varieties with detailed attributes
    - Amount (grams), alpha acid %, crop year, form (pellet/leaf/plug)
    - Storage location, purchase date, supplier tracking
    - Quick amount adjustment for usage tracking
    - Summary view with total weight and variety counts
  - **Yeast Inventory** - Track yeast strains with expiration and generation tracking
    - Link to yeast library strains or use custom names
    - Track quantity, form (dry/liquid/slant/harvested), expiry dates
    - Generation tracking for harvested yeast with source batch linking
    - Expiring soon warnings (configurable days threshold)
    - Harvest from batch functionality for yeast propagation
  - **Frontend UI** - Tabbed inventory management interface
    - Summary cards with statistics per category
    - Search and filter functionality
    - CRUD modals for all inventory types
    - Expiring yeast warnings display
  - **API Endpoints**
    - `GET/POST /api/inventory/equipment` - Equipment list and create
    - `GET/PUT/DELETE /api/inventory/equipment/{id}` - Equipment CRUD
    - `GET /api/inventory/equipment/types` - List equipment types
    - `GET/POST /api/inventory/hops` - Hops list and create
    - `GET/PUT/DELETE /api/inventory/hops/{id}` - Hops CRUD
    - `GET /api/inventory/hops/varieties` - List hop varieties
    - `GET /api/inventory/hops/summary` - Inventory statistics
    - `PATCH /api/inventory/hops/{id}/adjust` - Quick amount adjustment
    - `GET/POST /api/inventory/yeast` - Yeast list and create
    - `GET/PUT/DELETE /api/inventory/yeast/{id}` - Yeast CRUD
    - `GET /api/inventory/yeast/expiring-soon` - Expiring within N days
    - `GET /api/inventory/yeast/summary` - Inventory statistics
    - `PATCH /api/inventory/yeast/{id}/use` - Decrement quantity on use
    - `POST /api/inventory/yeast/harvest` - Create yeast from batch harvest
- **AI Assistant Inventory Tools** - LLM tools for querying inventory
  - `search_inventory_hops` - Search hop inventory by variety, form, minimum amount
  - `search_inventory_yeast` - Search yeast inventory with expiration filtering
  - `check_recipe_ingredients` - Check if ingredients are available for a recipe
  - `get_inventory_summary` - Get overview of all inventory categories
- **Mobile-Responsive Assistant Sidebar** - Improved assistant page for mobile devices
  - Collapsible sidebar (default collapsed on mobile)
  - Backdrop overlay for mobile sidebar
  - Dynamic viewport height support for mobile browsers
  - Responsive header and input area
  - Hidden input hints on small screens
- Recipe CRUD frontend UI
  - Manual recipe creation form with BeerJSON fields
  - Recipe edit functionality
  - Updated recipe detail page with BeerJSON field names (og, fg, abv, color_srm)
  - "New Recipe" and "Edit" buttons in navigation flow
- Multi-format recipe import: Support BeerXML (.xml), BeerJSON (.json), and Brewfather JSON (.json) files
- Backend auto-detects recipe format from file extension and content structure

### Changed
- Recipe import page now shows all supported formats in help text
- File picker accepts both .xml and .json files
- Assistant sidebar collapsed by default for better mobile experience

### Fixed
- **False Positive Stuck Fermentation Alerts** - Added lag phase protection to anomaly detector
  - No stuck fermentation alerts during first 24 hours of fermentation (configurable)
  - Prevents false positives when yeast is still in lag phase
  - Cleared existing false positive anomaly flags from database
- **LLM Thread Title Summarization** - Fixed to use configured LLM provider instead of hardcoded default
- **ML Prediction Reliability** - Improved early fermentation prediction handling
  - Added minimum progress threshold (5%) before trusting FG predictions
  - Fixed curve fitting lower bound to prevent unrealistic FG predictions (0.990 minimum)
  - Context-aware unavailability messages explaining why predictions aren't ready
- **Mobile Viewport Issues** - Fixed chat input requiring scroll on mobile devices
- **Library Page 404 on Refresh** - Added `/library` route to FastAPI for SPA navigation
- **ML Predictions Auto-Reload** - Predictions now load automatically without manual refresh
  - Frontend triggers reload on page load
  - Backend auto-reloads from database when in-memory pipeline is empty
- **AI Assistant ML Awareness** - Assistant now understands and explains ML prediction data
  - Documented Kalman-filtered readings, confidence scores, predicted FG
  - Explains when predictions are unavailable and why

### Technical
- New database tables: `equipment`, `hop_inventory`, `yeast_inventory`, `hop_variety`, `fermentable`
- New routers: `inventory_equipment.py`, `inventory_hops.py`, `inventory_yeast.py`, `hop_varieties.py`, `fermentables.py`
- Foreign key relationships: YeastInventory → YeastStrain, YeastInventory → Batch (for harvest tracking)
- Inventory AI tools integrated into LLM service tool definitions
- Frontend uses Svelte 5 reactive `$state` patterns for inventory management
- Prompty templates in `backend/services/llm/prompts/` for externalized AI prompts
- Renamed grain_varieties to fermentables throughout codebase for broader ingredient scope

## [2.8.0] - 2026-01-16

### Added
- **Yeast Library** (#82) - Comprehensive yeast strain database with 449+ strains from Beer Maverick
  - New `/yeast` page for browsing and searching yeast strains
  - Filter by producer, type (ale/lager/wild/hybrid), form (dry/liquid), and flocculation
  - Detailed strain cards showing temperature range, attenuation, alcohol tolerance
  - Full-text search across strain names and producers
  - Producer dropdown with all major yeast labs (White Labs, Wyeast, Fermentis, Lallemand, etc.)
- **Batch Yeast Assignment** - Assign yeast strains to batches independent of recipe
  - Yeast selector on batch create/edit forms
  - Override recipe yeast with specific strain from library
  - Yeast strain details displayed on batch detail page in Recipe Targets card
- **Beer Maverick Scraper** - `scripts/scrape_beermaverick.py` for updating yeast database
  - Scrapes 449+ strains with detailed fermentation data
  - Extracts: name, producer, product_id, type, form, temp range, attenuation, flocculation, alcohol tolerance, description
  - Outputs to `backend/seed/yeast_strains.json`
- **Yeast API Endpoints**
  - `GET /api/yeast` - List strains with filtering (search, producer, type, form, flocculation)
  - `GET /api/yeast/{id}` - Get strain details
  - `GET /api/yeast/producers` - List all producers
  - `POST /api/yeast/refresh` - Refresh database from seed file

### Changed
- Yeast database source changed from BrewUnited (223 strains) to Beer Maverick (449 strains)
- `alcohol_tolerance` field changed from float to string to support descriptive values (e.g., "medium", "high", "9-11%")

### Fixed
- **Yeast Library Pagination** - Fixed default limit of 100 preventing display of all strains
- **Schema Migration Safety** - Added safeguard to clear batch yeast references before dropping yeast_strains table
  - Prevents foreign key corruption when yeast IDs change during database refresh

### Technical
- New `backend/routers/yeast.py` router for yeast API endpoints
- New `frontend/src/routes/yeast/+page.svelte` for yeast library UI
- Database migration `_migrate_yeast_strains_alcohol_tolerance` handles schema change
- Yeast seeder in `backend/seed/yeast_seeder.py` loads strains on startup
- Beer Maverick scraper uses BeautifulSoup with rate limiting and parallel requests

### Data Quality (Beer Maverick)
- 449 unique yeast strains
- 98% have temperature ranges
- 89% have attenuation data
- 100% have flocculation data
- 100% have form (dry/liquid) data

## [2.7.0] - 2025-12-08

### Added
- **Tilt Calibration Page Migration** (#81) - Migrated from deprecated CalibrationPoint table to modern JSON-based Device.calibration_data API
  - Temperature calibration with independent SG and temperature calibration curves
  - Celsius storage with automatic C/F display conversion based on user preferences
  - Duplicate point detection with unit-aware tolerance (0.001 for SG, 0.1°C for temp)
  - Backend validation for SG range (0.990-1.200) and temperature range (-10°C to 50°C)
  - Comprehensive test coverage with 5 new backend tests (all passing)
  - ARIA labels for accessibility on all interactive elements
  - Optimized API calls (eliminated redundant GET on save)

### Fixed
- **Race Condition on Device Switching** - Fixed calibration data loading race when switching between devices
  - Form no longer displays stale data from previous device
  - Loading indicator prevents premature user interaction
- **Form State Leakage** - Clear form points completely when device changes
  - Prevents cross-device point contamination
  - Reset form to pristine state on device selection
- **Linear Calibration Validation** - Fixed incorrectly requiring SG points for temp-only calibration
  - Independent validation for SG and temperature curves
  - Allow pure temperature calibration without SG points
- **Outdated Comment** - Updated `backend/ingest/base.py:44` comment to reflect current Celsius-first architecture
  - Removed misleading "Always Fahrenheit after normalization" comment
  - Added accurate comment about Celsius storage standard

### Technical
- Calibration UI uses reactive Svelte 5 `$state` for form management
- Form points sync bidirectionally with Device.calibration_data JSON structure
- Validation uses Pydantic models with custom validators for range checking
- Test suite includes edge cases: empty calibration, single-point, duplicate detection, invalid ranges
- Linear interpolation algorithm matches deprecated table-based system for backward compatibility

## [2.6.0] - 2025-12-05

### Added
- **ML Pipeline Integration** (#66) - Integrated ML pipeline into production reading handler
  - MLPipelineManager now processes all readings through Kalman filter, anomaly detection, and predictions
  - Per-device ML state isolation prevents cross-contamination between Tilts
  - ML outputs (filtered values, confidence, anomaly flags, predictions) stored in database
  - WebSocket broadcasts include ML data for real-time frontend updates
  - Graceful degradation on ML errors (falls back to calibrated values)

### Fixed
- **Temperature Migration Edge Cases** - Fixed hysteresis conversion bugs
  - Lager temperatures at exactly 50°F now detected correctly (changed `>` to `>=`)
  - Orphaned hysteresis values (without temp_target) now detected and converted
  - Added explicit migration tracking via config table to prevent double-migration
  - Independent CASE statements prevent hysteresis/target coupling issues
- **Production Database Corruption** - Manually fixed corrupted hysteresis value (-17.48°C → 1.0°C)
  - Root cause: Old migration code used wrong formula `(F - 32) * 5/9` for delta values
  - Delta values should use `F * 5/9` (no -32 offset)
- **Anomaly Reasons Type Consistency** - Fixed unnecessary JSON encode/decode
  - Kept as list in memory, only JSON encode for database storage
  - WebSocket broadcasts use list directly (no decode needed)
- **Frontend Null Safety** - Added fallback defaults for temperature units
  - `formatTemp()` now handles undefined config gracefully
  - `getTempUnit()` defaults to 'C' if config not loaded

### Changed
- Replaced simple moving average smoothing with Kalman filtering
- Removed `backend/services/smoothing.py` (superseded by ML pipeline)
- Temperature migration now uses explicit config flag tracking
- All temperatures standardized to Celsius throughout system

### Technical
- ML pipeline processes readings after calibration but before storage
- Database schema includes new ML output columns (sg_filtered, temp_filtered, confidence, etc.)
- Frontend receives all temperatures in Celsius, converts for display
- Migration tracking prevents double-conversion on redeployment

## [2.5.0] - 2025-12-04

### Added
- **Machine Learning Pipeline** (#61) - Advanced fermentation monitoring with predictive analytics
  - **Kalman Filtering** - Noise reduction for SG/temperature/RSSI measurements with adaptive process noise scaling
  - **Anomaly Detection** - Automatic detection of stuck fermentation, temperature spikes, and signal drops
  - **Curve Fitting** - Exponential decay model for FG prediction and completion time estimation
  - **Model Predictive Control (MPC)** - Intelligent heater control with overshoot prevention (10x penalty)
  - **Per-Device State Isolation** - Separate ML pipeline instances per Tilt prevent cross-contamination
  - **Feature Flags** - Configurable enable/disable for each ML component via `MLConfig`
- **Thermal Model Learning** - MPC learns heating rate and cooling coefficient from historical data
  - Parameter estimation: `heating_rate` (°F/hour), `cooling_coeff` (dimensionless)
  - Receding horizon optimization with trajectory prediction (2-hour default)
  - Automatic model relearning as fermentation progresses
- **Validation System** - Comprehensive testing and validation tools
  - `validate_ml_isolation.py` script for Raspberry Pi validation
  - `ML_VALIDATION_GUIDE.md` with 5 validation methods
  - 48/48 ML tests passing (100% coverage)

### Fixed
- **Per-Device State Isolation** (Critical) - Fixed global pipeline state causing cross-contamination
  - Created `MLPipelineManager` to maintain separate pipelines per device_id
  - Each Tilt now has isolated Kalman filter, anomaly detector, curve fitter, and MPC controller
  - Prevents RED Tilt readings from corrupting BLUE Tilt state
- **MPC Ambient History Safety** (Major) - Fixed IndexError crash when ambient temps are missing
  - Added `min_history_len` calculation to align all histories before MPC learning
  - Slices `temp_history`, `heater_history`, `ambient_history` to same length
  - Gracefully handles missing ambient temperature data

### Technical
- New ML package structure in `backend/ml/`:
  - `config.py` - ML configuration with feature flags
  - `filters/kalman.py` - Extended Kalman filter implementation
  - `detection/anomaly.py` - Rule-based anomaly detection
  - `prediction/curve_fit.py` - Exponential decay curve fitting
  - `control/mpc.py` - Model Predictive Controller
  - `pipeline.py` - 4-stage orchestration (Kalman → Anomaly → Predictions → MPC)
  - `pipeline_manager.py` - Per-device pipeline management
- ML dependencies added: `numpy`, `filterpy`, `scipy`, `scikit-learn`
- Test suite: 48 tests across 6 test files
  - `test_kalman.py` - Kalman filter behavior
  - `test_anomaly.py` - Anomaly detection rules
  - `test_curve_fit.py` - Curve fitting accuracy
  - `test_mpc.py` - MPC controller optimization
  - `test_ml_pipeline.py` - Pipeline orchestration
  - `test_pipeline_manager.py` - Multi-device isolation
  - `test_mpc_ambient_history.py` - Safety edge cases

### Configuration
```python
from backend.ml.config import MLConfig

config = MLConfig(
    enable_kalman_filter=True,      # Noise reduction
    enable_anomaly_detection=True,  # Stuck fermentation detection
    enable_predictions=True,        # FG prediction
    enable_mpc=True,                # Intelligent heater control
)
```

### Usage Example
```python
from backend.ml.pipeline_manager import MLPipelineManager

manager = MLPipelineManager()

# Process RED Tilt reading
result = manager.process_reading(
    device_id="RED",
    sg=1.050,
    temp=68.0,
    rssi=-60,
    time_hours=24.0,
    ambient_temp=65.0,
    heater_on=True,
    target_temp=70.0,
)

# Returns:
# {
#   "kalman": {"sg_filtered": 1.0498, "temp_filtered": 68.1, ...},
#   "anomaly": {"is_anomaly": False, "reason": None},
#   "predictions": {"predicted_fg": 1.012, "hours_remaining": 72.5, ...},
#   "mpc": {"heater_on": True, "predicted_temp": 69.8, ...}
# }
```

### Deployment
- ML validation on Raspberry Pi confirmed:
  - ✅ Per-device isolation verified (RED/BLUE Tilts independent)
  - ✅ No MPC crashes with missing ambient temps
  - ✅ Service running without errors
  - ✅ All ML dependencies installed successfully

## [2.4.0] - 2025-12-04

### Added
- **Cooling Control Support** (#58) - Dual-mode temperature regulation with independent heater and cooler control
  - Per-batch cooler entity configuration (switch or input_boolean)
  - Symmetric hysteresis logic for both heating and cooling
  - Mutual exclusion enforcement (heater and cooler never run simultaneously)
  - Support for three operational modes: heating-only, cooling-only, or dual-mode
  - Minimum cycle time protection (5 minutes) for cooler compressor safety
  - Real-time cooler state display on batch detail page
  - Cooler entity selection dropdown on batch creation/edit forms
- **Batch Lifecycle Management** - Complete soft delete and data maintenance system
  - Tab-based navigation on batch list page (Active, Completed, Deleted)
  - Soft delete and restore functionality for batches
  - Hard delete option with cascade to readings
  - Data maintenance page for orphaned reading cleanup
  - Orphaned data detection and reporting
  - Preview-first cleanup pattern for safety
  - Convenience endpoints: `/api/batches/active` and `/api/batches/completed`
  - Maintenance API endpoints for data integrity
- **Chart Crosshair Tooltips** (#55) - Display exact reading values at crosshair position
  - Shows timestamp, gravity (with proper unit formatting), wort temperature, ambient temperature, and trend line values
  - Floating tooltip with semi-transparent background and backdrop blur for readability
  - No more guessing values from axis labels
- **Reading Smoothing at Source** (#55) - Moving average filter applied during BLE reading ingestion
  - Uses existing `smoothing_enabled` and `smoothing_samples` config settings from System page
  - Applied after calibration but before storage for consistent smoothed data across all consumers
  - Per-device buffers maintain recent readings for window calculation
  - Smoothed values stored in database benefit charts, exports, and Home Assistant integration

### Fixed
- **Batch Delete Button** - Fixed delete functionality that was broken due to URL construction error
  - Changed `deleteBatch()` to use relative URL string instead of `new URL()` constructor
  - `new URL()` requires absolute URLs but `BASE_URL` was relative (`'/api'`)
  - Replaced browser `confirm()` with modal dialog for better UX and reliability
  - Modal prevents event handler binding issues in Svelte 5

### Changed
- Batch list page now uses tab navigation instead of status filter chips
- Removed "archived" status in favor of soft delete pattern
- Default batch list now excludes deleted batches
- Enhanced batch filtering with `include_deleted` and `deleted_only` query parameters

### Fixed
- **Chart Outlier Spikes** (#55) - Physically impossible readings no longer corrupt charts
  - Added validation for SG range (0.500-1.200) and temperature range (32-212°F)
  - Invalid readings marked with `status='invalid'` and filtered from all API responses
  - Historical outliers cleaned up via migration (83 outliers marked invalid)
  - Charts now only display validated readings

### Migration
- Added `deleted_at` column to batches table
- Existing "archived" batches automatically migrated to "completed" status

### Technical
- Created `SmoothingService` with moving average algorithm in `backend/services/smoothing.py`
- Added outlier validation in `backend/main.py` `handle_tilt_reading()` function
- Updated `backend/routers/tilts.py` to filter `status='valid'` readings in all queries
- Migration script `backend/migrations/mark_outliers_invalid.py` to clean historical data
- uPlot legend enabled with live updates and custom tooltip styling
- New `backend/routers/maintenance.py` router for orphaned data management
- Soft delete logic in `backend/routers/batches.py` with cascade support

### Code Review Fixes (PR #56)
- **Database Migration**: Added status column migration with index for query performance in `backend/database.py`
- **Validation Order**: Moved outlier validation BEFORE smoothing to prevent invalid readings from contaminating moving average buffer
- **HTTP Device Support**: Extended validation and smoothing to HTTP ingestion path (iSpindel/GravityMon) in `backend/services/ingest_manager.py`
- **Config Caching**: Implemented 30-second cache for smoothing config to reduce DB queries from every-reading to periodic refresh
- **Null Safety**: Fixed smoothing service query to use `is not None` check instead of truthiness to handle edge cases with zero values
- **Buffer Cleanup**: Added automatic cleanup of inactive device buffers (1-hour TTL) to prevent memory growth
- **Data Migration**: Integrated historical outlier marking into `init_db()` for automatic cleanup on deployment

## [2.3.2] - 2025-12-03

### Added
- Modular card-based architecture for batch detail page
- Live readings card with calibrated and raw values
- Signal strength indicator with quality labels and dBm values
- Real-time ABV calculation during active fermentation: `(OG - Current SG) × 131.25`
- Real-time attenuation calculation during fermentation: `((OG - Current SG) / (OG - 1.000)) × 100%`
- Enhanced device status card with signal diagnostics
- Fermentation progress card with visual progress bar
- Clear visual distinction between live/in-progress and final values

### Changed
- Refactored batch detail page sections into reusable card components
- Improved responsive layout with better mobile experience
- FG now shows current gravity during fermentation (instead of "--")
- ABV and attenuation display live values during active fermentation

### Fixed
- Missing aria-label on delete button for accessibility
- Batch detail page now shows same diagnostic data as dashboard

### Technical
- Created 7 new Svelte components in `src/lib/components/batch/`
- Maintained backward compatibility with existing batch data
- Architecture ready for future AI assistant features

## [2.3.1] - 2025-12-03

### Fixed
- **Timezone Display Bug** (#42) - Fixed "Last Seen" times showing incorrect values (e.g., "11h ago" when device is actively transmitting)
  - All datetime fields now serialize with explicit UTC timezone indicator ('Z' suffix) per RFC 3339
  - Prevents JavaScript from misinterpreting UTC timestamps as local time
  - Applied consistently across all API responses, WebSocket broadcasts, and CSV exports
  - Added `serialize_datetime_to_utc()` helper function with comprehensive test coverage

## [2.3.0] - 2025-12-02

### Added
- Recipe library UI for BeerXML import and management (#32)
  - Import page with drag-and-drop BeerXML file upload
  - Recipe list with search and filter
  - Recipe detail view with fermentation-focused layout
  - Laboratory notebook aesthetic with amber accents
  - Integration with batch creation (auto-fill from recipe)
  - Crimson Pro serif font for recipe names
  - JetBrains Mono for measurements
- Device pairing workflow - devices must be paired before logging readings (#35)
  - New `/devices` page for managing paired and unpaired devices
  - Pairing status indicators on dashboard
  - API endpoints for pairing/unpairing devices (`POST /api/tilts/{id}/pair`, `POST /api/tilts/{id}/unpair`)

### Changed
- Readings are only stored for paired devices
- Batch creation only shows paired devices in device selector
- New devices are unpaired by default

### Migration
- Existing devices will be marked as unpaired after upgrade
- Users must manually pair devices to resume reading storage

### Fixed
- Systemd service now points to `.venv` so installs run with the correct virtualenv
- Installer copies frontend assets alongside backend for local installs and builds the frontend during installation

## [2.2.0] - 2025-12-02

### Added
- **Per-Batch Heater Control** (#29) - Independent temperature control for multiple simultaneous fermentations
- Batch-specific heater entity configuration (switch or input_boolean)
- Batch-specific temperature targets and hysteresis settings
- Manual override controls (Force ON/OFF) per batch with configurable duration
- Real-time heater state display with visual indicators on batch detail pages
- Temperature control card shows current heater state, target, and hysteresis per batch

### Technical
- Per-batch control loop processes all fermenting batches independently
- In-memory state tracking (`_batch_heater_states`, `_batch_overrides`) with automatic cleanup
- Database constraints prevent heater entity and device conflicts between fermenting batches
- Minimum cycle time protection (5 minutes) prevents rapid heater cycling
- WebSocket broadcasts for real-time heater state updates
- Comprehensive validation tests for heater entity format and conflict detection

### API Endpoints
- `GET /api/control/batch/{batch_id}/status` - Get temperature control status for specific batch
- `POST /api/control/override` - Set manual override (requires `batch_id` parameter)
- `GET /api/control/heater-entities` - List available switch/input_boolean entities from Home Assistant

### Breaking Changes
- Global heater override endpoint now requires `batch_id` parameter (legacy global control deprecated)
- Temperature control now operates per-batch instead of globally

## [2.1.0] - Unreleased

### Added
- **RSSI Signal Filtering** (#6) - Filter weak Bluetooth signals below configurable threshold to reduce noise
- **Plato/Brix Gravity Units** (#3) - Display gravity as SG, Plato (°P), or Brix (°Bx) with unit toggle in System settings

### Technical
- RSSI filter uses cached config (30s TTL) to minimize DB queries during high-frequency BLE scanning
- Gravity unit conversion functions added to frontend config store

## [2.0.0] - 2025-11-29

### Changed
- **Project Rebrand** - Renamed from "Tilt UI" to "BrewSignal" to reflect multi-device support

### BREAKING CHANGES

#### Environment Variables
- `TILT_MOCK` → `SCANNER_MOCK`
- `TILT_FILES` → `SCANNER_FILES_PATH`
- `TILT_RELAY` → `SCANNER_RELAY_HOST`

#### File Paths
- Database file renamed: `tiltui.db` → `fermentation.db`

#### System Service
- Systemd service renamed: `tiltui.service` → `brewsignal.service`
- Service users must reinstall/rename service files

#### Migration Notes
- Update environment variables in your deployment configuration
- Rename database file: `mv tiltui.db fermentation.db`
- Reinstall systemd service with new name
- Update any automation/scripts referencing old names

## [1.3.0] - 2025-11-29

### Added
- **Multi-Hydrometer Support** - Universal ingest layer for multiple device types
- **iSpindel Support** - HTTP POST endpoint for iSpindel WiFi hydrometers
- **GravityMon Support** - Extended iSpindel format with pre-filtered readings
- **Device Registry** - Unified device management for all hydrometer types
- **Device API** - CRUD endpoints for device management (`/api/devices`)
- **Polynomial Calibration** - Angle-to-gravity calibration for iSpindel-style devices
- **Unit Conversion** - Automatic Plato↔SG and Celsius↔Fahrenheit conversion

### Technical
- New `backend/ingest/` module with adapter pattern for device formats
- `HydrometerReading` dataclass for universal reading representation
- `IngestManager` service for reading pipeline (parse → calibrate → store → broadcast)
- Database migration adds `devices` table and new columns to `readings`
- Non-destructive migration preserves existing Tilt data
- 114 backend tests with full coverage of new ingest layer

### API Endpoints
- `POST /api/ingest/generic` - Auto-detect device format
- `POST /api/ingest/ispindel` - iSpindel HTTP endpoint
- `POST /api/ingest/gravitymon` - GravityMon HTTP endpoint
- `GET/POST/PUT/DELETE /api/devices` - Device management
- `GET/PUT /api/devices/{id}/calibration` - Device calibration data

## [1.2.1] - 2025-11-28

### Fixed
- **Chart Refresh Spam** - Charts no longer refresh constantly with BLE events
- Added 30-second minimum throttle between automatic data fetches
- User actions (time range, refresh setting, retry) still respond immediately

## [1.2.0] - 2025-11-28

### Changed
- **Compact Dashboard Layout** - Moved room ambient and weather forecast from large cards to compact top bar indicators
- Weather indicator shows today's forecast with expandable 5-day dropdown on click
- Ambient temperature/humidity now displays inline in navigation bar

### Technical
- New `weather.svelte.ts` store for centralized weather/alerts state management

## [1.1.0] - 2025-11-28

### Added
- **Home Assistant Integration** - Connect to Home Assistant for ambient temperature/humidity display
- **Temperature Control** - Automatic heater control via HA switch entity with hysteresis
- **Manual Override** - Force heater on/off for 1 hour, bypassing automatic control
- **Weather Forecast Display** - 5-day forecast from HA weather entity on dashboard
- **Predictive Weather Alerts** - Warnings when forecast temps may affect fermentation
- **Chart Timezone Support** - X-axis now respects system timezone setting

### Fixed
- HA client reinitialization when config changes
- Immediate heater action on manual override
- Timezone-aware datetime consistency throughout backend

## [1.0.1] - 2025-11-28

### Added
- Reading smoothing with configurable sample count (System settings)
- Chart smoothing applies moving average to SG and temperature data

### Fixed
- Temperature chart axis now uses minimum 10-degree range to reduce visual noise
- Settings validation and persistence (#8)
- Timezone selection persistence (#7)
- Beer name editing from dashboard (#2)

## [1.0.0] - 2025-11-28

### Added
- Real-time Tilt hydrometer monitoring dashboard
- BLE scanning using Bleak library for Tilt device detection
- WebSocket-based live updates to frontend
- SG and temperature calibration with linear interpolation
- Calibration point management (add, view, clear)
- Historical readings storage with SQLite/SQLAlchemy async
- CSV export of all readings
- Automatic data cleanup (30-day retention)
- Multi-mode scanner support:
  - BLE mode (production): Direct Bluetooth scanning
  - Mock mode: Simulated readings for development
  - File mode: Read from TiltPi JSON files
  - Relay mode: Fetch from remote TiltPi
- Systemd service for Raspberry Pi deployment
- Svelte frontend with responsive design
- REST API for tilts, readings, calibration, and system info

### Technical
- FastAPI backend with async SQLAlchemy 2.1
- Bleak BLE library with beacontools for iBeacon parsing
- SQLite database with automatic migrations
- WebSocket manager for real-time client updates
