# Solomon's Swarm — Frontend Design Guide

> **One-sentence brief:** Black tactical console, near-monochrome neutrals, a single
> orange accent for "live," everything labeled in tight uppercase, numbers tabular —
> a command center for summoned daemons.

## The vibe

A **tactical operations console**: dark, dense, mission-control energy applied to a
fleet of autonomous AI agents. Closer to NORAD / a hacker's situation room than a
friendly SaaS dashboard.

The name carries an **occult-sysadmin mythology** — a _daemon_ is both a background
process and a summoned spirit. The product is **Solomon's Swarm**; the individual
agents are **daemons**. The brand mark is the **Seal of Solomon** (the hexagram from
the grimoire tradition used to bind spirits), rendered as an animated sigil.

## Tokens

All design tokens live as CSS custom properties in [`src/index.css`](src/index.css)
and are exposed to Tailwind in [`tailwind.config.js`](tailwind.config.js). **Use the
tokens — don't hardcode hexes.**

### Color

| Role            | Token               | Value (HSL)        | Usage                              |
| --------------- | ------------------- | ------------------ | ---------------------------------- |
| Canvas          | `--surface-canvas`  | `0 0% 0%`          | App background (pure black)        |
| Panel           | `--surface-panel`   | `0 0% 9%`          | Cards, sidebar, toolbars           |
| Inset           | `--surface-inset`   | `0 0% 15%`         | Recessed / nested surfaces         |
| Hairline        | `--hairline`        | `0 0% 25%`         | Borders, separators                |
| Ink primary     | `--ink-1`           | `0 0% 100%`        | Values, headings                   |
| Ink label       | `--ink-2`           | `0 0% 64%`         | Labels                             |
| Ink muted       | `--ink-3`           | `0 0% 45%`         | Kickers, metadata                  |
| **Accent**      | `--accent-orange`   | `24.6 95% 53.1%`   | The one brand color — "live"/focus |
| Status online   | `--status-online`   | `142 64% 42%`      | Healthy / running                  |
| Status degraded | `--status-degraded` | `38 92% 50%`       | Warning / throttled / idle         |
| Status offline  | `--status-offline`  | `0 84% 60%`        | Down / error                       |

**The accent rule:** orange is the _only_ brand color and means "live / active / you
are here." Never introduce a second decorative accent. New colors may _only_ encode
status, and only from the three `--status-*` tokens. (Tailwind: `bg-status-online`,
`text-status-degraded`, etc.)

### Typography

Typeface is **Geist Mono** everywhere — the monospace reinforces the "machine
readout" identity and visually separates machine data from prose.

Codified type roles (component classes in `index.css`, prefer these over re-deriving):

- `.tac-kicker` — 0.62rem, semibold, uppercase, wide tracking, muted. Section eyebrows.
- `.tac-label` — xs, uppercase, tracking, neutral-400. Field/nav labels.
- `.tac-value` — 2xl, bold, white, **tabular-nums**. Big stat numbers.

Rules of thumb:

- **UPPERCASE + wide letter-spacing** (`0.08–0.22em`) for all labels, nav, kickers.
- **Tabular numerals** for any number that updates, so digits don't jitter.
- High contrast in _size_ (big white value over tiny muted label), low contrast in
  _color_.

### Shape & motion

- **Boxy:** 6px radii (`--radius`), borders over shadows. Bento-style fixed-min tiles.
- **Motion is signal, not decoration:** `animate-pulse` on live indicators, ~150ms
  color transitions. The sigil rotates slowly. Nothing bouncy. All looping motion is
  disabled under `prefers-reduced-motion`.

## Components

### Sigil — `src/components/brand/Sigil.tsx`

The animated Seal of Solomon: two interlocked triangles bound by counter-rotating
runic rings with a pulsing core. The visual anchor of the brand.

- `<Sigil size={300} />` — hero scale (login).
- `<Sigil size={40} />` — lockup scale (sidebar header).
- Accepts `animated={false}` to freeze (also auto-frozen under reduced-motion).

### Status dot — `.status-dot`

`<span className="status-dot" data-status="online | degraded | offline" />`. Pulls
its color from the `--status-*` tokens via `data-status`. Pair with `animate-pulse`
for "live."

### Daemon grid — `.daemon-grid`

The faint summoning-grid canvas texture (44px grid + soft orange top glow on black).
Applied to the app shell and the login hero.

## Voice & mythology conventions

- **Product** = "Solomon's Swarm." **Agents** = "daemons." A group is "the swarm."
- Prefer summoning vocabulary for agent lifecycle where it reads naturally:
  **summon** (start), **banish** (stop), **bind** (configure). Keep destructive and
  financial actions plainly worded — don't let theme obscure consequence.
- Status copy is terse and uppercase: `SWARM ONLINE`, `SWARM IDLE`.

## Quick checklist for any new screen

1. Background is the canvas/panel scale; separate with hairlines, not shadows.
2. One orange accent for "live"; status colors only from the three status tokens.
3. Labels/kickers uppercase + tracked via `.tac-*`; numbers tabular.
4. Motion only as signal, and reduced-motion safe.
