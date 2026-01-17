# BrewSignal Open Core Roadmap
**Date:** 2026-01-17
**Strategy:** Polish local first, then monetize cloud features that are "too hard to DIY"

---

## Philosophy

**Open Core Model:**
- Local app is fully-featured, open source, amazing
- Cloud features solve problems that require infrastructure: notifications, remote access, sync, aggregated data
- We don't cripple local to force cloud - we make cloud genuinely valuable

**"Best Brewing App" Vision:**
BrewSignal should be the only app a homebrewer needs from recipe planning through fermentation to packaging.

---

## Current State Assessment

### What's Already Great
- Real-time fermentation monitoring with ML intelligence
- Multi-device support (Tilt, iSpindel, GravityMon)
- Temperature control via Home Assistant
- AI brewing assistant with context awareness
- Recipe import (BeerXML, BeerJSON, Brewfather)
- Comprehensive ingredient library (hops, yeast, fermentables)
- Fermentation predictions and anomaly detection

### What's Missing for "Best App"
- Recipe builder/calculator (compete with BeerSmith)
- Brew day workflow (timers, checklists, temp schedules)
- Water chemistry calculator
- Inventory tracking with low-stock alerts
- Carbonation/priming calculator
- Batch comparison and analytics
- Mobile-first experience (PWA)

---

## Phase 1: Core Polish (Next 4-6 weeks)

**Goal:** Make the existing features rock-solid and delightful.

### 1.1 Reliability & Performance
| Issue | Priority | Cloud Hook |
|-------|----------|------------|
| BLE Scanner Watchdog and Auto-Recovery (tilt_ui-hhr) | P2 | None - just reliability |
| Data Lifecycle Management (tilt_ui-exb) | P1 | Cloud: "Unlimited history retention" |
| Automated Database Backup (tilt_ui-a6z) | P3 | Cloud: "Automatic cloud backup" |

### 1.2 UX Polish
| Issue | Priority | Cloud Hook |
|-------|----------|------------|
| Quick Actions from Dashboard Cards (tilt_ui-so8) | P3 | None |
| Fermentation Notes and Event Logging (tilt_ui-34j) | P2 | Cloud: "Sync notes across devices" |
| Rename to 'Fermentation Intelligence' (tilt_ui-gtg) | P3 | Branding |

### 1.3 Recipe Experience
| Issue | Priority | Cloud Hook |
|-------|----------|------------|
| Enhance recipe CRUD frontend (tilt_ui-crx) | P2 | None |
| Add recipe export endpoint (tilt_ui-40f) | P2 | None |
| Add diverse example recipes (tilt_ui-8o5) | P2 | None |

---

## Phase 2: Differentiation Features (6-10 weeks)

**Goal:** Features that make BrewSignal the "smart" brewing app.

### 2.1 Analytics & Insights
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Batch Comparison View** (tilt_ui-gas) | Side-by-side fermentation curves | Cloud: "Compare to community averages" |
| **Health Dashboard** (tilt_ui-4lw) | System status, sensor health | None |
| **Yeast Performance Tracking** | NEW: Track attenuation by yeast strain over time | Cloud: "Community yeast benchmarks" |

### 2.2 Brew Day Support (NEW)
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Brew Day Timer** | Step-by-step mash schedule with notifications | Cloud: "Push notifications to phone" |
| **Mash Calculator** | Water volumes, strike temp, infusion steps | None - BeerSmith replacement |
| **Boil Timer** | Hop addition countdown, whirlpool timing | Cloud: "Push notifications" |
| **Checklist System** | Pre-brew, brew day, post-brew checklists | Cloud: "Sync across devices" |

### 2.3 Recipe Builder (NEW - Big Feature)
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Visual Recipe Editor** | Drag-drop ingredients, real-time calculations | None - this is the hook |
| **Style Guidelines** | BJCP style targets, color preview | None |
| **Scaling Calculator** | Batch size scaling with efficiency adjustment | None |
| **AI Recipe Generation** | "Make me a hazy IPA" → full recipe | Cloud: "AI included" |

---

## Phase 3: Complete Brewing Toolkit (10-16 weeks)

**Goal:** Eliminate need for any other brewing software.

### 3.1 Water Chemistry (NEW)
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Water Profile Database** | Common city profiles, brewing targets | None |
| **Salt Additions Calculator** | Gypsum, calcium chloride, etc. | None |
| **Mash pH Estimator** | Based on grain bill and water | None |
| **Source Water Input** | Save your tap water report | Cloud: "Sync across devices" |

### 3.2 Inventory Management (Enhance Existing)
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Full Inventory Tracking** | All ingredients with quantities, locations | Cloud: "Sync, share with brew partner" |
| **Low Stock Alerts** | Warn when running low on staples | Cloud: "Push notifications" |
| **Recipe Availability Check** | "Can I brew this with what I have?" | None |
| **Shopping List Generation** | Missing ingredients → list | None |

### 3.3 Packaging & Carbonation (NEW)
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Priming Calculator** | Sugar amount by style and volume | None |
| **Forced Carbonation Chart** | PSI/temp/volumes interactive chart | None |
| **Keg Tracker** | What's on tap, when tapped, remaining | Cloud: "Share tap list" |

---

## Phase 4: Mobile & Connectivity (16-20 weeks)

**Goal:** Best-in-class mobile experience, setting up cloud hooks.

### 4.1 Progressive Web App
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **PWA Installation** (tilt_ui-wj8) | Add to home screen, app-like experience | Foundation for push |
| **Offline Mode** | View recent data without network | Cloud: "Real-time sync when online" |
| **Responsive Polish** | Mobile-first dashboard redesign | None |

### 4.2 Notifications Foundation
| Feature | Description | Cloud Hook |
|---------|-------------|------------|
| **Push Notifications** (tilt_ui-91a) | Browser push for local | Cloud: "Works from anywhere" |
| **Alert Configuration UI** | Choose what triggers alerts | Cloud: "SMS alerts" |
| **Quiet Hours** | Don't alert at 3am | None |

---

## Cloud Features (Post-Local Polish)

These features are deliberately "too hard to DIY" and justify the subscription:

### Tier 1: BrewSignal Cloud ($70/yr)
| Feature | Why it's hard to DIY |
|---------|---------------------|
| **Remote Access** | Port forwarding, dynamic DNS, SSL, security |
| **Push Notifications** | Firebase setup, certificates, maintenance |
| **SMS Alerts** | Twilio account, costs, spam protection |
| **AI Assistant Included** | We pay for LLM API, no key management |
| **Community Benchmarks** | Aggregated data from all users |
| **Cross-Device Sync** | Real-time sync, conflict resolution |
| **Forever History** | Cloud backup, searchable archive |

### Tier 2: BrewSignal Pro ($130/yr)
| Feature | Why it's valuable |
|---------|------------------|
| **Unlimited Batches** | Power users, nano-breweries |
| **API Access** | Custom integrations |
| **Advanced Analytics** | ML-powered insights, trends |
| **Priority AI** | Faster, longer context |

---

## Immediate Next Steps

### This Week
1. **Start Phase 1.1** - BLE Watchdog (tilt_ui-hhr) for reliability
2. **Start Phase 1.2** - Fermentation Notes (tilt_ui-34j) for UX
3. **Create backlog items** for new features identified above

### This Month
1. Complete Phase 1 core polish
2. Begin Batch Comparison View (tilt_ui-gas)
3. Design Recipe Builder architecture

### This Quarter
1. Ship Recipe Builder MVP
2. Ship Brew Day Timer
3. Launch PWA

---

## Success Metrics

**Local App Quality:**
- Zero crashes in 30 days
- < 2 second page load
- BLE reconnection within 60 seconds
- User completes full brew cycle without leaving app

**Cloud Conversion (Future):**
- 5% of local users sign up for cloud trial
- 20% trial → paid conversion
- < 5% monthly churn

---

## Architecture Notes

### Code Organization
```
backend/
├── services/
│   ├── brewing/           # NEW: Calculations (mash, water, carbonation)
│   ├── inventory/         # Enhance existing
│   ├── recipes/           # Enhance: builder logic
│   └── llm/              # Existing AI
├── routers/
│   ├── calculators.py     # NEW: Brewing calculators API
│   └── brew_day.py        # NEW: Timers, checklists
```

### Shared Code for Cloud
The following will be extracted to shared modules for cloud reuse:
- ML pipeline
- Brewing calculations
- Recipe parsing/validation
- AI prompts (already Prompty format)

---

## Appendix: Feature-to-Backlog Mapping

### Existing Issues (Ready)
- tilt_ui-91a: Push Notifications
- tilt_ui-exb: Data Lifecycle Management
- tilt_ui-4lw: Health Monitoring Dashboard
- tilt_ui-34j: Fermentation Notes
- tilt_ui-gas: Batch Comparison View
- tilt_ui-hhr: BLE Scanner Watchdog
- tilt_ui-a6z: Automated Database Backup
- tilt_ui-wj8: PWA with Offline Support
- tilt_ui-so8: Quick Actions
- tilt_ui-gtg: Rename to Fermentation Intelligence

### New Issues Needed
- Recipe Builder (visual editor, calculations)
- Brew Day Timer & Checklists
- Mash Calculator
- Water Chemistry Calculator
- Priming/Carbonation Calculator
- Keg Tracker
- Inventory Low Stock Alerts
- Yeast Performance Tracking
