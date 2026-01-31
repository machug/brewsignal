# BrewSignal Monetization Strategy v2
**Date:** 2026-01-17
**Updated:** 2026-01-18
**Status:** Draft - Two-track model for technical and non-technical users

---

## Target Audiences

### Audience A: Technical Homebrewers (Free Tier)
- Already own Raspberry Pi, sensors, fermentation chamber
- Comfortable with Home Assistant, networking, command line
- Enjoy tinkering and customization
- Want full control over their setup

### Audience B: Non-Technical Homebrewers (Paid Tier)
- Want monitoring without the complexity
- Don't own (or want to manage) a Raspberry Pi
- Willing to pay for convenience
- May not have Home Assistant or desire to set it up

---

## The Home Assistant Challenge

**Current state:** Temperature control relies on Home Assistant integration for:
- Controlling smart plugs (heater/cooler switching)
- Reading ambient temperature sensors
- Automation rules and hysteresis logic

**The problem:** Home Assistant requires significant technical setup. Non-technical users won't do this.

**Solution:** Phased approach - start with monitoring-only SaaS, add hardware control later.

---

## Revised Product Tiers

### Tier 1: BrewSignal Local (Free, Open Source)

**Target:** Technical homebrewers (Audience A)

**What it is:** The current RPi application, downloadable and self-hosted.

**Features:**
- All monitoring, ML, and temperature control features
- AI Assistant with BYOK (user provides OpenAI/Anthropic/Gemini API key)
- Unlimited batches, recipes, devices
- Home Assistant integration for full automation
- Data stored locally

**Requirements:**
- Raspberry Pi (or similar Linux device)
- Technical comfort with setup
- Home Assistant (optional, for temp control)
- Own network infrastructure

**Our role:** Provide software, documentation, community support

---

### Tier 2: BrewSignal Cloud ($8/mo or $70/yr)

**Target:** Non-technical homebrewers (Audience B)

**What it is:** Fully hosted monitoring platform - no Raspberry Pi needed.

**Phase 1 Features (MVP - Monitoring Only):**
- **Direct device connection** - iSpindel/GravityMon push data straight to our cloud
- **Tilt support via phone app** - User runs lightweight Tilt relay app on old phone/tablet
- **Full dashboard** - Real-time gravity, temperature, fermentation progress
- **ML predictions** - FG estimates, completion time, anomaly detection
- **AI Assistant included** - We pay for the LLM, no API key hassle
- **Smart alerts** - SMS/push: "Your beer is at 74°F, yeast prefers 65-68°F - consider adjusting"
- **Recipe management** - Import BeerXML/BeerJSON, track batches
- **Forever data retention** - All your brew history, searchable
- **Community benchmarking** - "Your fermentation is 15% faster than average for this yeast"

**Phase 1 Limitations:**
- **No automated temperature control** - We alert, you act manually
- User still needs hydrometer hardware (Tilt, iSpindel, or GravityMon)

**Optional:** Users with Home Assistant can still integrate it themselves for temp control - we just don't require it.

**Phase 2 Features (Future - With Gateway Hardware):**
- **BrewSignal Gateway** - Optional hardware for full automation
- **Automated heater/cooler control** - Cloud sends commands to gateway
- **Local control loop** - Fast response times, works during internet outages

**Equipment Guide (with affiliate links):**
- Tilt Hydrometer (~$135) or iSpindel kit (~$50-80)
- Optional: WiFi temperature sensor for ambient readings
- Optional: BrewSignal Gateway for automated control (Phase 2)

**Our role:** Host everything, provide AI, send alerts, guide equipment choices

---

### Tier 3: BrewSignal Pro ($15/mo or $130/yr)

**Target:** Serious hobbyists, multi-batch brewers, small nano-breweries

**Features:**
- Everything in Cloud tier, plus:
- **Unlimited simultaneous batches** (Cloud = 3 max)
- **API access** - Build custom integrations
- **Advanced analytics** - Batch-over-batch comparisons, trend analysis
- **Priority AI** - Faster responses, longer context
- **White-glove onboarding** - Video call setup assistance
- **Priority support** - Response within 24 hours

---

### Tier 4: BrewSignal Team ($30/mo)

**Target:** Brewing clubs, shared fermentation spaces, small commercial

**Features:**
- Everything in Pro, plus:
- 5 user seats (additional seats $5/mo each)
- Multiple location support
- Shared recipe library with permissions
- Activity audit log
- Dedicated support channel

---

## Technical Architecture

### Phase 1: Monitoring Only (No Local Hardware Required)

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Home                               │
│                                                              │
│  ┌─────────────┐         ┌─────────────┐                    │
│  │  iSpindel   │────────▶│   WiFi      │                    │
│  │  GravityMon │  HTTP   │   Router    │                    │
│  └─────────────┘         └──────┬──────┘                    │
│                                 │                            │
│  ┌─────────────┐         ┌──────┴──────┐                    │
│  │    Tilt     │◀───BLE──│ Phone/Tablet│ (Tilt relay app)   │
│  └─────────────┘         └──────┬──────┘                    │
│                                 │                            │
└─────────────────────────────────┼────────────────────────────┘
                                  │ HTTPS
                                  ▼
                ┌──────────────────────────────────┐
                │       BrewSignal Cloud           │
                │                                  │
                │  ┌────────────────────────────┐  │
                │  │ Ingest API                 │  │
                │  │ - /api/v1/ispindel         │  │
                │  │ - /api/v1/gravitymon       │  │
                │  │ - /api/v1/tilt-relay       │  │
                │  └────────────────────────────┘  │
                │                                  │
                │  ┌────────────────────────────┐  │
                │  │ Core Services              │  │
                │  │ - User Auth (Clerk)        │  │
                │  │ - ML Pipeline              │  │
                │  │ - AI Assistant (LLM)       │  │
                │  │ - Alert Engine (Twilio)    │  │
                │  │ - Data Storage (Postgres)  │  │
                │  └────────────────────────────┘  │
                │                                  │
                │  ┌────────────────────────────┐  │
                │  │ Web Dashboard              │  │
                │  │ app.brewsignal.com         │  │
                │  └────────────────────────────┘  │
                └──────────────────────────────────┘
```

**Key insight:** iSpindel and GravityMon already support custom HTTP endpoints. User just enters `https://api.brewsignal.com/v1/ispindel?token=xxx` in their device config. No RPi needed.

**Tilt challenge:** Tilt is BLE-only, needs a local device to relay. Options:
1. Lightweight phone/tablet app (most users have an old phone lying around)
2. Cheap ESP32 relay device (~$15)
3. BrewSignal Gateway (Phase 2)

---

### Phase 2: With Gateway Hardware (Future)

**Hardware Decision (Jan 2026):** NodeMCU ESP32-E WROOM (~$15 AUD) with Shelly smart plugs for temperature control. No relay modules needed - ESP32 controls Shelly plugs directly via local HTTP API.

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Home                              │
│                                                                  │
│   Tilt ──BLE──▶ ESP32 Gateway ──────────────────────────────────┼──┐
│                      │              (NodeMCU ESP32-E, ~$15)      │  │
│                      │                                           │  │
│                      ├──HTTP──▶ Shelly plug (heater)            │  │
│                      └──HTTP──▶ Shelly plug (cooler)            │  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘  │
                                                                      │
                    WebSocket (persistent, bidirectional)             │
                    wss://api.brewsignal.com/gateway                  │
                                                                      │
┌──────────────────────────────────────────────────────────────────┐  │
│                      BrewSignal Cloud                             │◀─┘
│                                                                   │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│   │ WebSocket   │    │   API       │    │  Database   │         │
│   │ Server      │◀──▶│   Server    │◀──▶│  (Postgres) │         │
│   └─────────────┘    └─────────────┘    └─────────────┘         │
│                            ▲                                      │
│                            │                                      │
│                     ┌──────┴──────┐                              │
│                     │  Dashboard  │                              │
│                     │  (Web App)  │                              │
│                     └─────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
```

**Communication Protocol:**
- ESP32 initiates WebSocket connection to cloud (outbound, bypasses NAT)
- **Readings UP:** `{"type": "reading", "temp": 18.5, "gravity": 1.042, "device": "tilt_orange"}`
- **Commands DOWN:** `{"type": "command", "action": "set_target", "temp": 18.0}`
- ESP32 authenticates with device token provisioned during setup

**Gateway features:**
- Receives Tilt BLE broadcasts locally
- Controls Shelly plugs via local HTTP API (no cloud dependency for switching)
- Maintains WebSocket connection to cloud for sync + commands
- Runs hysteresis logic locally (fast response, no cloud latency)
- Works offline (maintains last known target, buffers readings)
- OTA firmware updates from cloud

**Recommended Shelly models:**
- Shelly Plug S (~$35 AUD) - plug-in, up to 2500W
- Shelly Plus 1PM (~$30 AUD) - hardwired with power monitoring

---

## Revenue Model

### Pricing Summary

| Tier | Price | Target | Key Value |
|------|-------|--------|-----------|
| Local | Free | Technical users | Full DIY, BYOK AI |
| Cloud | $70/yr | Non-technical | Monitoring + AI, no hardware setup |
| Pro | $130/yr | Serious hobbyists | Unlimited batches, API, priority |
| Team | $360/yr | Clubs/commercial | Multi-user, multi-location |

### Revenue Projections (Year 1)

**Conservative scenario:**
- 500 free/local users (community, word of mouth)
- 50 Cloud subscribers @ $70 = $3,500
- 20 Pro subscribers @ $130 = $2,600
- 2 Team subscribers @ $360 = $720

**Year 1 ARR: ~$6,800**

### Cost Structure (Monthly)

| Item | Cost |
|------|------|
| Cloud hosting (Railway/Render) | $30-50 |
| Database (Supabase/Neon) | $25 |
| LLM API (OpenAI/Anthropic) | $50-100 |
| Twilio (SMS alerts) | $20-50 |
| Auth (Clerk) | $0-25 |
| Domain/SSL | $5 |
| **Total** | **$130-255/mo** |

**Break-even:** ~25-45 Cloud subscribers

### Hardware Revenue (Phase 2)

| Product | Cost | Price | Margin |
|---------|------|-------|--------|
| BrewSignal Gateway (ESP32-E) | ~$15 | $45 | $30 |
| Gateway + Case + Cable kit | ~$20 | $55 | $35 |

**Note:** No relay modules included - users purchase Shelly smart plugs separately (~$35 each). This keeps our hardware simple and avoids mains wiring liability.

**Affiliate revenue:**
- Tilt Hydrometer: ~5-10% commission (~$7-14 per sale)
- iSpindel kits: ~5-10% commission
- Shelly smart plugs: ~5-10% commission (~$3-4 per sale)
- Fermentation equipment (chambers, heating pads, etc.)

---

## Implementation Roadmap

### Phase 1: Cloud Monitoring MVP (Q1 2026)

**Goal:** Validate demand with monitoring-only SaaS

**Backend:**
- [ ] Multi-tenant database schema (user_id on all tables)
- [ ] User auth integration (Clerk or similar)
- [ ] iSpindel-compatible ingest endpoint (`/api/v1/ispindel`)
- [ ] GravityMon-compatible ingest endpoint
- [ ] Tilt relay endpoint (for phone app)
- [ ] ML pipeline running in cloud
- [ ] Alert engine (email first, then SMS)

**Frontend:**
- [ ] Landing page with pricing
- [ ] User registration / onboarding flow
- [ ] Cloud dashboard (fork of current frontend)
- [ ] Device setup wizard ("Enter this URL in your iSpindel...")
- [ ] Alert configuration UI

**AI:**
- [ ] Server-side AI assistant (no BYOK)
- [ ] User context injection (their batches, recipes, history)

**Infrastructure:**
- [ ] Deploy to Railway/Render
- [ ] Postgres database
- [ ] Stripe billing integration
- [ ] Basic monitoring/logging

**Deliverable:** Working SaaS that iSpindel/GravityMon users can sign up for

---

### Phase 2: Tilt Support & Enhanced Alerts (Q2 2026)

**Goal:** Support Tilt users, improve alerting

- [ ] Tilt relay mobile app (React Native or Flutter)
- [ ] Or: ESP32 Tilt relay firmware (cheap hardware option)
- [ ] SMS alerts via Twilio
- [ ] Push notifications (PWA)
- [ ] Anomaly detection alerts
- [ ] "Beer ready" predictions with notifications

---

### Phase 3: Community & Benchmarking (Q3 2026)

**Goal:** Differentiate with community intelligence

- [ ] Anonymous data aggregation (opt-in)
- [ ] "Compare to community" feature
- [ ] Yeast performance statistics
- [ ] Recipe success rates
- [ ] Public recipe sharing (optional)

---

### Phase 4: Gateway Hardware (Q4 2026)

**Goal:** Enable full automation for paid users

- [ ] Design ESP32-based gateway
- [ ] Firmware development (BLE scan, relay control, cloud sync)
- [ ] Manufacturing partnership or DIY kit
- [ ] Cloud-to-gateway command protocol
- [ ] Local control loop with cloud override
- [ ] Gateway setup wizard in app

---

## Competitive Positioning

### vs Brewfather ($25-40/yr)
- **They:** Beautiful UI, passive dashboard, no AI
- **We:** AI assistant included, proactive alerts, predictions
- **Message:** "Brewfather shows you data. BrewSignal tells you what to do."

### vs BeerSmith ($35 one-time)
- **They:** Recipe math gold standard, desktop-first, no monitoring
- **We:** Real-time monitoring + AI insights
- **Message:** "BeerSmith plans your brew. BrewSignal watches it ferment."

### vs DIY (Free)
- **They:** Full control, unlimited customization, time investment
- **We:** Works out of the box, we handle the complexity
- **Message:** "Your time is worth more than $6/month."

---

## Open Questions

1. **Tilt relay strategy:** Phone app vs cheap ESP32 device vs both?
   - Phone app: Most users have old phones, zero hardware cost
   - ESP32: More reliable, always-on, but user must buy/flash it

2. **Pricing validation:** Is $70/yr right for monitoring-only?
   - Lower than Brewfather but no recipe tools (yet)
   - AI assistant is unique value

3. **Gateway timing:** Build hardware in-house or partner?
   - In-house: Control, margins, but hardware is hard
   - Partner: Faster, but dependency

4. **Free tier cannibalization:** Will technical users just use free forever?
   - That's fine - they're not the paid tier target anyway
   - Free users become evangelists, some convert when life gets busy

---

## Next Steps

1. **Validate demand:**
   - [ ] Create landing page with email capture
   - [ ] Post to homebrewing Reddit/forums
   - [ ] Gauge interest before building

2. **Technical spike:**
   - [ ] Test iSpindel direct-to-cloud ingestion
   - [ ] Prototype multi-tenant schema
   - [ ] Estimate cloud costs with realistic load

3. **MVP scope lock:**
   - [ ] Define exact Phase 1 feature set
   - [ ] Timebox to 6-8 weeks of development
   - [ ] Launch to waitlist for beta feedback
