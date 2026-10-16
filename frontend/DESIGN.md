# SpecTrace frontend: design direction

> Status: design direction for the first release. There were no separate brand guidelines, so it was derived from the product itself: a tool for reading evidence. Any decision below can be replaced.

Audience and style: API and documentation engineers reviewing a change before release, in an evidence-ledger style (a printed audit document, with a monospaced face for data). Calm, low motion, moderate density.

## Product context

- **Product:** compares two versions of OpenAPI files and Markdown docs, lists what changed, and shows which docs, requirements and examples depend on each change, with the source line that proves it.
- **User:** a backend or API engineer, or a technical writer, who must decide what to re-check before a release.
- **Primary action:** add two versions, compare, read the evidence for one change.
- **Trust requirement:** high. Every impact must show how it was found. A guess must never look like a fact.
- **Platform:** responsive web, used mostly on a laptop, readable on a phone.
- **Not a landing page.** The product is the tool; there is no marketing hero.

## Direction: Evidence Ledger (Developer Tool)

A reviewed document, not a dashboard. Hairline rules, a heavy rule above each section, mono for keys, paths and line numbers, and the cited source line shown with its gutter. Density is moderate: the page is for reading.

## Why each major decision

| Decision | Reason |
|---|---|
| Warm paper background and ink text, dark variant by system setting | The tool is for reading long diffs and citations; paper tones are easier for long reading than pure white, and the dark variant follows the user's system. Both themes are tested. |
| One accent, deep teal | Links and the single primary action. Not purple/indigo; teal separates "actions" from the red/amber/green used only for meaning. |
| Red, amber, green used only for meaning | Breaking, needs review, non-breaking. Always paired with a shape and a text label, never color alone. |
| Confirmed = solid outline, inferred = dashed outline | The product's central claim is the difference between confirmed and inferred. Border style plus the word carries it in any theme and for color-blind users. |
| IBM Plex Sans and IBM Plex Mono | Plex Mono has distinct `0`/`O` and `1`/`l` shapes, which matters when reading entity keys and line numbers. Using one family keeps the page consistent. |
| Heavy 2px rule above each section, hairlines inside | Identity motif: the printed ledger. It also gives hierarchy without cards or shadows. |
| No cards, no shadows, no glass, no glow, 2px radius | Hierarchy comes from rules, type size and spacing. Nothing floats. |
| Two-pane review layout from 900px | A list of changes beside the evidence for the selected one; stacked on narrow screens. |
| Motion: 100ms color change on hover and focus only | Motion has no job here beyond confirming interaction. Reduced-motion users get none. |

## Tokens

| Token | Light | Dark |
|---|---|---|
| `--paper` | `#F4F1E8` | `#14130F` |
| `--surface` | `#FBF9F3` | `#1C1B16` |
| `--ink` | `#1B1A16` | `#ECE8DB` |
| `--ink-2` (secondary text) | `#4A473F` | `#B5B0A0` |
| `--rule` (decorative hairline) | `#D6D0C0` | `#34322A` |
| `--edge` (control borders, markers; at least 3:1) | `#7A7566` | `#8A8574` |
| `--accent` | `#0B5F5F` | `#5CC4C0` |
| `--breaking` | `#A4261C` | `#FF8A7E` |
| `--review` (needs review) | `#7A4F00` | `#E0AE5A` |
| `--ok` | `#276238` | `#7FCB8E` |

All text pairs were computed with the WCAG 2 contrast formula: body 15.4:1, secondary 8.2:1, accent 6.6:1, red 6.5:1, amber 6.3:1, green 6.4:1 on paper in light; every dark pair is above 7.5:1. Control borders are 4.1:1 or better.

Spacing: 4px base (4, 8, 12, 16, 24, 32, 48). Radius: 2px only. Type: Plex Sans 16px body, 14px secondary, Plex Mono 13.5px for data; headings 28/20/16 semibold.

## Layout strategy

- **Compare page:** two version panes side by side (stacked on phones), one primary action, then a ledger table of earlier comparisons.
- **Run page:** summary strip, question box, then a change ledger (left) and evidence detail (right).
- **Benchmark page:** one table per claim, with the caveats stated beside the numbers.

## Copy rules

Specific verbs ("Compare versions", "Load petstore example"). No buzzwords, no em dashes, no invented numbers: every figure on screen comes from the API or the stored benchmark file. Empty, loading and error states say what happened and what to do.

## Known trade-offs

- Not Tailwind or a component library, so more custom CSS to maintain.
- The theme follows the system until a choice is made; the choice is stored in the browser only.
- Drag and drop is an extra. The file and folder buttons remain the primary, single-pointer way to add files.
