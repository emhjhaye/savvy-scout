Savvy Scout — Design System (quick reference)

1. Brand tokens
- Primary: Deep Navy: #071428
- Accent (CTA / highlight): Vivid Pink: #FF2D58
- Secondary (insight): Teal: #00BFA6
- Neutral dark: #22252A
- Neutral mid: #9AA3AD
- Background: #F4F6F8 (light contexts) / layered navy for dashboard

2. Typography
- Headings: Poppins (Google) — 600/700 for H1-H3
- Body & UI: Inter — 400/500 for body, labels
- Fallback stack: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
- Responsive sizing: use clamp() for large displays and scale down on mobile

3. Spacing & grid
- Base spacing unit: 8px
- Layout container: max-width 1180px, side padding 24px
- Border radius: 8px for UI cards, 999px for pill buttons

4. Buttons
- Primary (CTA): background: var(--accent), color: #fff, padding: 10–14px, border-radius: 999px
- Secondary (outline): transparent background, 1px border rgba(255,255,255,0.12), color: #fff
- Disabled: 45% opacity, pointer-events: none

5. Forms & inputs
- Height: 44px; padding: 10px 12px; border-radius: 8px
- Focus: 2px outline using --accent with 0.18 alpha
- Validation: error border #FF4D4F and accessible text under input

6. Sidebar & navigation
- Width: 260–300px for desktop
- Compact icons + label; collapsed state shows icons only
- Active nav highlight: small 4px left accent bar + bold label

7. Cards & panels
- Use subtle glass/overlay on dark hero/dashboard: rgba(255,255,255,0.02)
- Elevation: soft shadow for CTA panels (0 6px 18px rgba(accent, 0.14))

8. Colors usage rules
- Use accent sparingly for CTAs, important numbers, and highlighted words in headings
- Use teal for supportive status or informational badges
- Reserve vivid pink for primary actions and key emphasis only

9. Accessibility notes
- Ensure contrast ratio >= 4.5:1 for body text on backgrounds
- Provide focus styles and keyboard support for all interactive controls

10. Component list to implement next
- Header (logo, global nav, account menu)
- Sidebar (queues, filters, admin link)
- Queue list item (ref, title, buyer, deadline, tags, triage badges)
- Notice detail (full text, gates, outcomes, brief generator, escalate button)
- Inline triage controls (Pass / Flag / Reject / Escalate)

11. Quick CSS variables (example)
:root {
  --brand-primary: #071428;
  --brand-accent: #FF2D58;
  --brand-secondary: #00BFA6;
  --neutral-900: #22252A;
  --neutral-500: #9AA3AD;
  --bg: #041226;
}

Notes
- These files are a starting point. After reviewing the prototypes, convert tokens to a shared CSS/SCSS module or a component library (Tailwind config, CSS custom properties, or design tokens JSON) as preferred.