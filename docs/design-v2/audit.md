# Design v2 — Impeccable audit of the current dashboard (before)

Branch `design-v2` from `reactor-hardware` (b2b83b8). Surface mode: **Operate** (dashboard, shown on a projector).
Engine of Impeccable not run (it downloads a closed binary); the audit follows `reference/audit.md` by hand,
with our own measurements: `tests/contrast-scan.mjs` (rendered contrast, opacity included),
`scripts/check-contrast.mjs` (tokens), `tests/overflow.mjs` (390 px), `tests/design-shots.mjs` (text < 13 px).
Screens "before": `docs/design-v2/before/<section>-<ru|kk|en>.png` (1366×768, full page).

## Audit health score

| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 | Disabled relay buttons look like active primary buttons (2.5:1, filled green) |
| 2 | Performance | 3 | Reactor bars animate `width`; two infinite animations |
| 3 | Theming | 2 | Tokens exist, but ~150 hex colours outside `:root` + 27 in TSX; no own font |
| 4 | Responsive | 3 | No page overflow at 390 px in RU/KZ; wide reactor table scrolls in its box |
| 5 | Implementation integrity | 3 | One coherent v10 system; drift is local (listed below) |
| **Total** | | **14/20** | **Good** — weakest: theming |

## Findings

- **[P1] Disabled controls read as enabled** — `Reactor.tsx` relay cards, automation, E-STOP, reset.
  With no Pi link the «Включить» buttons stay filled green at 2.5:1; on a projector a farmer reads them as clickable.
  Fix: disabled = outline/ghost + lock icon + text that says why. → `polish`.
- **[P2] Global reduced-motion kill** — `styles.css`: `*{animation:none!important;transition:none!important}`.
  Also removes state feedback (relay switching, tabs). Fix: keep fades/colour changes, drop movement. → `animate`.
- **[P2] Hard-coded colours** — styles.css 74, agentChat.css 23, reactor.css 19, design.css 23 (some are tokens), TSX 27;
  `#55d6af` 16× outside tokens. A theme swap leaves old mint in nav, badges, charts. → `extract`/`colorize`.
- **[P2] System font only** — `Segoe UI`; look and Kazakh glyphs depend on the laptop. Fix: self-hosted font files
  in the bundle (offline), tabular figures for readings. → `typeset`.
- **[P2] Footer text 4.17:1, divider 1.07:1** — below 4.5:1. → `polish`.
- **[P2] Layout animation** — `reactor.css` `transition: width .6s`; use `transform: scaleX`. → `optimize`.
- **[P3] Repeated identical card grids** on Overview (4 + 4 same-shape cards) and tracked capital eyebrows. → `layout`.

## Positive

Token file with a 13 px floor and checked contrast; `MotionConfig reducedMotion="user"`; skip link; focus rings
on design-system buttons; no horizontal scroll on phones; all three languages fit.

## Plan (after the theme is chosen)

Roles: Impeccable = audit + polish; theme-factory = one theme (custom, its own themes are for slides);
Emil = motion; Taste/frontend-design = composition only. Conflicts: projector readability > farmer clarity > beauty.

1. Tokens: one theme in `design.css` (+ `--ok`, `--font-sans`, `--font-mono`), replace hard-coded colours, local fonts in `src/fonts/`.
2. Overview → 3. AI Chat (thinking feed, message entrance) → 4. Reactor (disabled states, relay switch feedback,
   bars via transform, alarm) → 5. Substrates & mixtures → 6. Market, Sources, System, Demo.
7. Motion (Emil): ≤ 200 ms UI, ease-out, transform/opacity only, `prefers-reduced-motion` keeps fades.
8. Checks: vitest, tsc, i18n-check, contrast-scan, design-shots (13 px), smoke all sections, agent eval via HTTP, Reactor on live Pi.
