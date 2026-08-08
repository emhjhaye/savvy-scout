# Savvy Scout — Complete Design Implementation Guide

**Date:** 19 July 2026  
**Version:** 1.0  
**Status:** Ready for front-end build

---

## Overview

This guide documents the complete user experience design for Savvy Scout, from login through daily operations. The app has been designed as a **role-based workflow system** with distinct interfaces for:

1. **Sector Owners** (Mark, Kanvesh, Hammad) — Approve notices, review AI assessments
2. **Victoria Milan (Bid Director)** — Make strategic bid/no-bid decisions on escalations
3. **System Admin** — Configure rules, manage data sources, audit logs

---

## Files Included

### HTML Templates (in `design/`)

| File | Purpose | Role | Status |
|------|---------|------|--------|
| `login.html` | Sign-in page | All | ✓ Existing |
| `dashboard-home-enhanced.html` | Main queue dashboard | Owners + Victoria | ✓ **New** |
| `notice-detail--phase1.html` | Phase 1 triage review | Owners | ✓ **New** |
| `notice-detail--phase2.html` | Phase 2 AI assessment review | Owners | ✓ **New** |
| `escalation-queue.html` | Escalation queue (FLAGs + owner marks) | Victoria | ✓ **New** |
| `pipeline.html` | Approved opportunities tracker | Owners | ✓ **New** |
| `admin.html` | System administration settings | Victoria | ✓ **New** |
| `design-tokens.css` | Design system variables | All | ✓ Existing |
| `components.css` | Reusable UI components | All | ✓ Existing |

---

## Key Design Decisions

### 1. **Color System**
- **Primary (Deep Navy):** `#071428` — Background, headings
- **Accent (Vivid Pink):** `#FF2D58` — CTAs, highlights (use sparingly)
- **Teal:** `#00BFA6` — Status badges (PASS, APPROVE), positive actions
- **Orange:** `#FFB47A` — Warning (FLAG, urgent)
- **Red:** `#FF4D4F` — Danger (FAIL, REJECT)
- **Muted Gray:** `#9AA3AD` — Secondary text

### 2. **Typography**
- **Headings:** Poppins (Google Fonts), 600–700 weight
- **Body/UI:** Inter, 400–500 weight
- **Responsive:** Use `clamp()` for fluid sizing
- **Fallback stack:** `system-ui, -apple-system, "Segoe UI", Roboto`

### 3. **Spacing & Layout**
- **Base unit:** 8px (use multiples: 8, 12, 16, 20, 24, 32, etc.)
- **Container max-width:** 1180px
- **Sidebar width:** 260–300px
- **Grid gap:** 20–32px (context-dependent)

### 4. **Component Patterns**

#### Status Badges
```html
<span class="status-badge status-pass">PASS</span>
<span class="status-badge status-flag">FLAG</span>
<span class="status-badge status-fail">FAIL</span>
```

#### Action Buttons
```html
<!-- Primary CTA -->
<button class="action-btn primary">✓ APPROVE</button>

<!-- Danger -->
<button class="action-btn danger">✗ REJECT</button>

<!-- Warning -->
<button class="action-btn warning">⚠ Escalate</button>
```

#### Queue Items
```html
<div class="queue-item">
  <div class="queue-item-content">
    <div class="queue-item-ref">REF-066188</div>
    <div class="queue-item-title">Opportunity Title</div>
    <div class="queue-item-meta">Buyer • Value • Deadline</div>
  </div>
  <div class="queue-item-status">
    <span class="status-badge">PASS</span>
    <a href="#" class="queue-item-action">Review →</a>
  </div>
</div>
```

---

## Page Flow

### Login (Starting Point)
**File:** `login.html`
```
┌─────────────────────────────┐
│ Savvy Scout Login           │
│ Sign in to the dashboard    │
│                             │
│ [Username: mark]            │
│ [Password: ***]             │
│ [Sign in]                   │
│                             │
│ Use: Mark, Kanvesh,         │
│      Hammad, Victoria       │
└─────────────────────────────┘
      ↓
   [Redirect based on role]
```

### Sector Owner Workflow
```
Dashboard (queue tabs)
   ├→ New (Phase 1)
   │   └→ notice-detail--phase1.html
   │       ├ [Gate results display]
   │       └ [Approve / Reject / Escalate buttons]
   │
   ├→ In Review (Phase 2)
   │   └→ notice-detail--phase2.html
   │       ├ [AI assessment display]
   │       └ [Accept / Reject / Escalate buttons]
   │
   ├→ Awaiting Approval
   │   └ [Rarely shown — items awaiting owner's click]
   │
   └→ Pipeline
       └→ pipeline.html
           ├ APPROVED (awaiting docs)
           ├ DOCS_DOWNLOADING
           ├ CALENDARED
           ├ ACTIVE (in pursuit)
           ├ PARKED
           └ REJECTED
```

### Victoria Workflow
```
Dashboard (Escalations link)
   └→ escalation-queue.html
       ├ [FLAGs from all gates]
       ├ [Owner-marked items]
       └ [Per item: View Brief → Approve / Park / Reject]
           └→ escalation-brief.html (ten sections)
               ├ Opportunity summary
               ├ Buyer
               ├ Value
               ├ Route to market
               ├ Gate outcomes
               ├ Provisional ratings
               ├ Competitor picture
               ├ Risks
               ├ Open questions
               └ Recommended next action
```

### Admin Workflow (Victoria Only)
```
admin.html
   ├ Sources & Health
   │   ├ Toggle: Find a Tender API
   │   ├ Toggle: Contracts Finder API
   │   └ Manual sweep button
   │
   ├ Gate Rules
   │   ├ Gate 1: Sector → Owner mapping
   │   ├ Gate 5: CPV code classification
   │   └ Save & version history
   │
   ├ Email Whitelist
   │   ├ Add/remove @bidsavvy.io addresses
   │   └ Test email button
   │
   └ Audit Log
       ├ All status changes logged
       ├ User, timestamp, reason
       └ Searchable & filterable
```

---

## Interaction Patterns

### Tabs (Used on Detail Pages)
```html
<div class="tabs">
  <div class="tab active" onclick="showTab(event, 'details')">
    Opportunity Details
  </div>
  <div class="tab" onclick="showTab(event, 'gates')">
    Gate Results
  </div>
  <div class="tab" onclick="showTab(event, 'json')">
    Full JSON
  </div>
</div>

<div id="details" class="tab-content active">...</div>
<div id="gates" class="tab-content">...</div>
<div id="json" class="tab-content">...</div>

<script>
  function showTab(e, tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    e.target.classList.add('active');
  }
</script>
```

### Modals (Decision Dialogs)
Used for:
- Confirming approval/rejection (requires reason)
- Escalating to Victoria (requires reason)
- Making Victoria decisions (approve/park/reject with reason)

**Pattern:** Click button → Modal overlay → Required reason field → Submit

---

## Status Transitions

### Notice Status Flow
```
NEW
  ↓ (Phase 1 gate results)
PHASE1_TRIAGED
  ↓ (Sector owner approves)
AWAITING_PHASE1_APPROVAL → [APPROVED / REJECTED]
  ↓
PHASE2_SCOPED
  ↓ (AI assessment generated)
AWAITING_PHASE2_APPROVAL → [APPROVED / REJECTED]
  ↓
ESCALATED_TO_VICTORIA
  ↓ (Victoria decides)
APPROVED → DOCS_DOWNLOADED → CALENDARED → ACTIVE
           or
           PARKED
           or
           REJECTED
```

**Color coding during flow:**
- Gray (NEW, in progress)
- Orange (awaiting decision)
- Green (APPROVED, ACTIVE)
- Red (REJECTED)
- Muted (PARKED)

---

## Responsive Design

### Breakpoints
- **Desktop:** >= 1200px
  - Full sidebar (260px)
  - 2-column layouts
  - Multi-column queues
  
- **Tablet:** 768px – 1199px
  - Sidebar collapses to icons
  - 1-column layouts
  - Single-column queues
  
- **Mobile:** < 768px
  - Hamburger menu
  - Full-width stacks
  - Larger touch targets (44px minimum)

### Responsive Patterns Used
```css
/* Flexible grid */
.content-wrapper { 
  display: grid; 
  grid-template-columns: 1fr 380px;
  gap: 32px;
}

@media (max-width: 1200px) {
  .content-wrapper { 
    grid-template-columns: 1fr;
  }
}

/* Fluid typography */
h2 {
  font-size: clamp(24px, 5vw, 32px);
  line-height: 1.2;
}
```

---

## Accessibility Features

✓ **Keyboard Navigation**
- Tab through all interactive elements
- Enter/Space to activate buttons
- Escape to close modals

✓ **Focus Indicators**
- 2px outline using accent color
- Visible focus state on all inputs

✓ **Color Contrast**
- >= 4.5:1 for body text
- Status badges provide text + color differentiation

✓ **ARIA Labels**
- `role="main"`, `role="navigation"` used
- Form labels associated with inputs
- Status badges have clear text

✓ **Screen Reader Support**
- Semantic HTML (`<main>`, `<aside>`, `<form>`)
- Descriptive link text ("Review →" not "Click here")
- Form error messages announced

---

## Integration Checklist

### Before Deployment

- [ ] Test all tab switching on Phase 1 & 2 detail pages
- [ ] Verify modal form validation (reason fields required)
- [ ] Confirm API integration points:
  - Queue data population
  - Gate results display
  - AI assessment display
  - Escalation brief generation
  - Audit log retrieval
  
- [ ] Test responsive design on:
  - Desktop (1920px, 1366px, 1024px)
  - Tablet (768px)
  - Mobile (375px, 414px)
  
- [ ] Browser compatibility:
  - Chrome 90+
  - Firefox 88+
  - Safari 14+
  - Edge 90+
  
- [ ] Performance:
  - Page load < 2s
  - Tab switching < 100ms
  - Modal open/close < 300ms

---

## Implementation Notes

### Data Binding
Each page expects JSON data structures:

**Notice Detail (Phase 1):**
```json
{
  "ref": "066188",
  "title": "Cloud Migration...",
  "buyer": "City of London Corporation",
  "indicative_value": "1200000-1800000",
  "cpv_codes": ["72200000"],
  "uk_stage": "UK3",
  "deadline": "2026-08-15T17:00:00Z",
  "gates": [
    {
      "gate_number": "gate1",
      "gate_name": "Sector & Owner",
      "outcome": "PASS",
      "reason": "Local Government + IT Services → Mark"
    }
  ]
}
```

**Assessment (Phase 2):**
```json
{
  "capability_fit_rating": "HIGH",
  "capability_fit_reasoning": "...",
  "right_to_win_rating": "MEDIUM",
  "right_to_win_reasoning": "...",
  "overall_rating": "PURSUE",
  "overall_reasoning": "...",
  "open_questions": ["Q1", "Q2", "Q3"]
}
```

---

## CSS Classes Reference

### Layout
- `.app` — Main flex container
- `.main` — Main content area
- `.sidebar` — Left navigation
- `.content-wrapper` — Two-column layout

### Typography
- `.ref` — Reference ID styling
- `.notice-title` — Large title
- `.meta-label`, `.meta-value` — Key-value pairs

### Status/Badges
- `.status-badge.status-pass` — Green
- `.status-badge.status-flag` — Orange
- `.status-badge.status-fail` — Red

### Components
- `.queue-item` — Opportunity card
- `.tab`, `.tab-content` — Tab system
- `.action-btn.primary`, `.action-btn.danger` — Button variants
- `.modal`, `.modal-content` — Modal overlay

---

## Next Steps

1. **Set up static file serving** in Flask
   - Place CSS files in `savvy_scout/static/design/`
   - Place HTML templates in `savvy_scout/templates/`

2. **Integrate data endpoints**
   - Route `/api/notice/<id>/phase1` → notice-detail--phase1.html
   - Route `/api/notice/<id>/phase2` → notice-detail--phase2.html
   - Route `/api/escalations` → escalation-queue.html
   - Route `/api/pipeline` → pipeline.html

3. **Add authentication middleware**
   - Protect all routes with login check
   - Role-based access control (redirect non-Victoria users from `/admin`)

4. **Test end-to-end workflows**
   - Owner: Login → Review Phase 1 → Approve → Review Phase 2 → Accept
   - Victoria: Login → View Escalations → Review Brief → Approve/Park/Reject
   - Admin: Login → Update rules → View audit log

5. **Performance & UX refinement**
   - Optimize image loading
   - Lazy-load queue items
   - Prefetch related data on hover

---

## Support & Questions

Refer to `design-system.md` for detailed token definitions.  
Refer to `USER_FLOWS.md` for detailed user journey maps.

All designs follow the SPEC.md requirements and non-negotiable rules (never invent data, whitelist email, label assessments as PROVISIONAL, etc.).

---

**Design approved for build: 19 July 2026**
