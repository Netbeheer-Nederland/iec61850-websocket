# HMI Style Guide & Design Documentation

This documents the actual, current visual language of the `hmi/` React
frontend: the design tokens it uses, the component patterns already built
on top of them, and the conventions to follow when adding new UI. It
describes what's really in `hmi/src/assets/styles.css` and `index.css`
today (including a couple of known inconsistencies - called out explicitly
rather than glossed over) so it stays trustworthy as a reference.

## Where things live

| File | Role |
|------|------|
| `hmi/src/assets/styles.css` | The stylesheet - design tokens (`:root`), layout, and every shared component class (`.btn-*`, `.form-group`, `.table`, `.modal-*`, etc.) |
| `hmi/src/index.css` | Vite/React boilerplate reset only - not part of the design system |
| Inline `style={{ ... }}` in JSX | Used throughout for one-off layout tweaks (flex gaps, spacing) and small pieces of dynamic/conditional styling (e.g. a status dot's color). Not wrong, but prefer a token (`var(--...)`) over a literal color even inline |

There's no component library or CSS-in-JS - just class names from
`styles.css` plus inline styles. Keep new UI consistent with that.

## Design tokens

Defined as CSS custom properties on `:root` at the top of `styles.css`:

```css
--primary-color: #2563eb;   --primary-dark: #1e40af;   --primary-light: #3b82f6;
--secondary-color: #7c3aed;
--success-color: #10b981;   --warning-color: #f59e0b;
--danger-color: #ef4444;    --info-color: #0ea5e9;

--bg-dark: #0f172a;   --bg-darker: #020617;
--bg-card: #1e293b;   --bg-hover: #334155;

--text-primary: #f1f5f9;   --text-secondary: #cbd5e1;   --text-muted: #94a3b8;

--border-color: #334155;   --border-light: #475569;

--sidebar-width: 280px;    --header-height: 70px;

--shadow-sm / --shadow-md / --shadow-lg: layered rgba(0,0,0,...) shadows
--transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

**Always reference these by name** (`var(--text-muted)`, `var(--bg-card)`)
rather than hardcoding a hex value - several places in the codebase
already don't (see [Known issues](#known-issues) below), and that's
exactly what makes the palette hard to change confidently.

### Color usage

| Token | Use for |
|-------|---------|
| `--primary-color` / `--primary-dark` / `--primary-light` | Primary actions, links, focus rings, the active nav item |
| `--secondary-color` | Rare - largely unused in current pages |
| `--success-color` | Connected/healthy status, success alerts |
| `--warning-color` | Degraded/attention-needed status |
| `--danger-color` | Disconnected/error status, destructive actions |
| `--info-color` | Informational badges/messages |
| `--bg-dark` / `--bg-darker` | Page background, header background |
| `--bg-card` | Panels, modals, tables, and (see below) read-only fields |
| `--bg-hover` | Editable field backgrounds, hover states, table header |
| `--text-primary` / `--text-secondary` / `--text-muted` | Primary content / secondary content / hints, placeholders, disabled text - in decreasing emphasis |
| `--border-color` / `--border-light` | Default borders / hover-state borders |

### Spacing & radius

No spacing scale variables exist - values are literal pixels chosen
per-component (`8px`, `12px`, `16px`, `20px`, `24px`, `32px` show up
most often, generally increasing with the size of the element). Border
radius is similarly ad hoc but consistent in practice: `8px` for buttons
and inputs, `10px`-`12px` for cards/modals/tables, `50%` for circular
elements (status dots, avatars).

When adding new UI, pick from the values already used nearby rather than
introducing a new one.

## Typography

- Base font: system font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, ...`), set once on `body`.
- No named type scale - headings are sized ad hoc:  `.page-header h1` is `28px`/`700`, `h2` inside a modal is `18px`/`600`. Follow the nearest existing heading of the same importance rather than picking a new size.
- Body text is generally `14px`; secondary/meta text (badges, hints, table headers) drops to `11px`-`13px`.

## Layout patterns

- **`.container`**: the app shell - a full-height flex row of `.sidebar` + `.main-content`.
- **`.sidebar`**: fixed-width (`--sidebar-width`) nav rail; `.sidebar-nav` holds the page links.
- **`.header`**: fixed-height (`--header-height`) top bar inside `.main-content`, holds the breadcrumb/title and header-level actions (`.header-actions`, built from `.btn-icon`s).
- **`.page-header`**: the per-page title row - `display:flex; justify-content:space-between`, an `<h1>` on the left and page-level actions (typically a `.btn-primary`, e.g. "Add Connection") on the right.
- Multi-field rows (like the FSP/SO instance forms) use an ad hoc flex row (`display:flex; gap:16px; flexWrap:wrap`) of `.form-group`s rather than a grid class - see `ACSIServer.jsx`'s connection section for the current best example, including stacking two such rows vertically when a selector (Instance) should sit above the fields it fills in.

## Components

### Buttons

| Class | Use for |
|-------|---------|
| `.btn-primary` | The primary action on a page or modal (Save, Add, Register, Start) |
| `.btn-secondary` | Secondary/cancel actions (Close, alternate action) |
| `.btn-icon` | Icon-only actions (refresh, edit, delete, TLS/OAuth config toggles) - `40x40px`, transitions to `--primary-color` background on hover |
| `.btn-close` | The `&times;` modal-close button specifically |

All three (`.btn-primary`/`.btn-secondary`/`.btn-icon`) already handle
their own `:disabled` and `:hover:not(:disabled)` states - don't
re-implement disabled styling per-button.

### Forms (`.form-group`)

The standard pattern for every labeled field:

```jsx
<div className="form-group">
  <label htmlFor="host">Host</label>
  <input type="text" id="host" value={formData.host} onChange={handleInputChange} />
</div>
```

- `label` is a block above the input (`margin-bottom: 8px`), not inline beside it.
- `input`/`select` share one look: full width, `10px 12px` padding, `8px` radius, `var(--border-color)` border, `var(--bg-hover)` background.
- Focus state: `var(--primary-color)` border + a soft blue glow (`box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1)`), no browser default outline.
- A one-line explanatory hint under a field (e.g. "Port this instance's own BFF server listens on...") is currently written as an inline-styled `<small style={{ color: 'var(--text-muted)' }}>`, not a shared class - match that pattern until/unless it's promoted to a `.form-hint` class (see [Known issues](#known-issues)).

#### Editable vs. read-only vs. disabled fields

Three distinct situations come up, and they should be visualized
differently - conflating them is what this section exists to prevent:

1. **A real, user-editable field.** Plain `<input>`/`<select>`, no `readOnly`/`disabled`. Gets the standard look above.
2. **A value that's fixed by other state, not user choice** - e.g. ACSI role and WebSocket Mode are fully determined by the connection `type` for RTI-SO/RTI-FSP (only meaningful as a real choice for a "Generic" connection). Render these as a **read-only `<input readOnly>`** showing the resolved value as text, not a disabled `<select>` - a disabled dropdown still visually reads as "a control you might be able to open," where a read-only text field reads as "this is just information." See `ConnectionModal.jsx`'s ACSI/WebSocket Mode fields for the reference implementation (branches on whether the type is Generic).
3. **A field temporarily locked** - e.g. inputs disabled while a save/start request is in flight (`disabled={loading}`). Use `disabled`, not `readOnly`, since the whole point is "you can't interact with this right now," not "this value is just informational."

Both `:read-only` and `:disabled` states share one visual treatment
(added specifically to make this distinction visible - see the "Style
readonly/disabled form fields" commit):

```css
.form-group input:read-only,
.form-group input:disabled,
.form-group select:disabled,
.form-group textarea:read-only,
.form-group textarea:disabled {
    background: var(--bg-card);   /* recedes vs. --bg-hover on editable fields */
    color: var(--text-muted);
    border-style: dashed;
    cursor: not-allowed;
}
```

`--bg-card` is deliberately different from the `--bg-hover` editable
fields use, and the dashed border is a second, redundant cue (don't rely
on color alone) - both together make a locked field noticeably different
from an editable one at a glance, which the bare browser default did not.

### Tables

```jsx
<div className="connections-table">
  <table className="table">
    <thead><tr><th>...</th></tr></thead>
    <tbody><tr><td>...</td></tr></tbody>
  </table>
</div>
```

`.connections-table` is the card-like wrapper (background, border,
rounded corners, clipped overflow); `.table` is the actual table
(header row uses `--bg-hover`, rows highlight `--bg-hover` on hover, all
cells get a `--border-color` bottom border). Despite the name,
`.connections-table` is used as the generic "table in a card" wrapper,
not something specific to the Connections page.

### Modals

```jsx
<div className="modal active">
  <div className="modal-content">
    <div className="modal-header"><h2>Title</h2><button className="btn-close">&times;</button></div>
    <div className="modal-body">...form-groups...</div>
    <div className="modal-footer"><button className="btn-secondary">Close</button><button className="btn-primary">Save</button></div>
  </div>
</div>
```

`.modal` is the full-screen dim overlay (only rendered/shown via the
`active` class - conditionally mount the `.modal` div in JSX rather than
toggling `display` yourself). `.modal-content` is the centered panel
(`--bg-card`, `500px` max width, slide-up entrance animation).
`.modal-footer` right-aligns its buttons with a secondary action first,
primary action last.

### Status indicators

- **Dot** (`.bff-status-dot`): a `10px` circle, `--danger-color` by default, `--success-color` when `.connected`. Used next to connection names/instance selectors throughout - some pages apply the class name and set the background inline instead of relying on `.connected`, but the visual result is the same.
- **Badge** (`.endpoint-card-status`): a pill (`padding: 4px 12px`, `12px` radius) with a solid background - `--success-color` normally, `--danger-color` with a `.disconnected` modifier on the parent.

Both patterns only encode two states (ok/not-ok) via color. If a third
state is ever needed (e.g. "connecting"), don't just invent a new color
inline - add it as a token first.

### Cards

`.endpoint-card`: the connection/instance summary card used on
Setup/Traffic pages - an icon tile (`.endpoint-card-icon`, solid
`--primary-color`, swaps to `--warning-color` via `.disconnected`), a
name + description, and a status badge, laid out as a horizontal flex
row with a hover lift (border + glow, matching the button/input focus
treatment).

## Known issues

Documenting these here so they don't get mistaken for intentional design
choices, and so a fix - if someone takes it on - has a clear before/after
to point at:

1. **A second, later `:root` block silently overrides part of the first.** Around `styles.css:1370` (in the "ACSI Client - IEC 61850 Client Page Styles" section) there's a *second* `:root { ... }` block that redeclares `--primary-color`, `--text-primary`, `--text-muted`, `--border-color`, etc. with different values (e.g. `--text-muted` becomes `#888888` there instead of the `#94a3b8` declared at the top of the file). Because both are plain `:root` rules of equal specificity, the later one wins in the cascade for every property it redeclares - so the *effective* value of several tokens throughout the app is actually set by this second block, not the one at the top that looks authoritative. Anyone tuning colors needs to check both blocks, not just the one at the top of the file.
2. **Several component classes are defined more than once.** `.page-header`, `.form-group`/`.form-group input`, and `.btn-primary`/`.btn-secondary` each have 2-3 separate rule blocks scattered through the file (e.g. `.form-group input` at lines ~786, ~1123, and ~1447) with slightly different values. This is almost certainly leftover from merging page-specific styles that predated a shared stylesheet. They don't currently conflict badly enough to be visibly broken, but editing "the" definition of one of these classes means finding *all* of its definitions, not just the first match.
3. **No spacing/typography scale.** Pixel values for padding, gaps, and font sizes are chosen ad hoc per component (see [Spacing & radius](#spacing--radius) and [Typography](#typography)). Consistent in practice by convention/copy-paste, not enforced by any shared scale.
4. **Field help text has no shared class.** The `<small style={{ color: 'var(--text-muted)' }}>` pattern used for inline field hints (WS Port, BFF Port, etc.) is copy-pasted per occurrence. Worth promoting to a `.form-hint` class if it grows beyond a handful of uses.

None of these block day-to-day work - just be aware of them (especially
#1 and #2) before assuming a value you see at the top of the file is the
one actually in effect.
