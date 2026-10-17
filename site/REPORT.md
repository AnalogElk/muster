# Responsive design overhaul report

Date: 2026-07-25

## Outcome

The responsive audit now reports `horizontalPageScroll: false` for all 21 page and viewport combinations. Every final `pageScrollWidth` equals its `clientWidth`.

The redesign keeps the paper, pine, ember, editorial type, mono evidence blocks, and Build-Trail identity. No visible copy changed.

## What changed

### Topbar

- The section nav now collapses below 1050px, which removes the 768px build-log failure.
- Below 600px, the brand and primary live link remain while secondary document links leave the sticky bar. Those links remain available in page content.
- The bar, brand, nav links, and buttons use constrained flex sizing and 44px minimum control heights.
- A single 80px document scroll offset clears the measured 60px sticky bar. Settled anchor checks at 375px, 768px, and 1280px placed targets at 80px, 20px below the bar.
- The previous `body { overflow-x: hidden; }` mask was removed. The clean result therefore comes from fitting and containment, not clipping the page.

### Code blocks

Code is mobile-first now. At widths through 820px, `pre.code` uses `pre-wrap` plus safe breaking, so long comments and commands wrap inside the console without changing the underlying copied text. Wider layouts retain preformatted lines and a bounded horizontal-scroll fallback.

The code regions are focusable for keyboard access. The generated whitepaper uses the same behavior through `build-paper.py`, and its nested `code` no longer compounds the font size below 14px.

This approach was chosen over mobile horizontal scrolling because the install and connection commands are primary content. They remain visible in one reading flow at 375px, while CSS-only wrapping preserves copy and paste.

### Tables

All proof tables remain inside bounded `.table-wrap` regions. The wrappers now have explicit width containment, touch overscroll containment, keyboard focus, a region role, and an accessible label. The whitepaper generator emits the same markup.

The build-log proof table remains wider than the phone viewport by 89px, 74px, and 52px at 375px, 390px, and 412px. That overflow belongs to the focusable table region and does not widen the document. This preserves a real row and column table instead of converting evidence into visually reordered cards.

### Type and targets

- A shared 14px floor now covers small editorial, mono, table, code, rail, and footer text.
- The final audit has zero `tinyText` entries across all 21 combinations.
- Explicit controls use a shared 44px minimum target: skip links, topbar brand and nav, buttons, live and snapshot chips, back links, footer links, and the print button.

## Measurements

Cells show document `scrollWidth` before and after. The viewport width is in each column heading. The before numbers are from the supplied live audit. The after numbers are from the final local loopback-origin audit. Every after value equals the viewport width and every final `horizontalPageScroll` value is `false`.

| Page | 375 | 390 | 412 | 768 | 1280 | 1440 | 1920 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `/` | 451 to 375 | 450 to 390 | 451 to 412 | 768 to 768 | 1280 to 1280 | 1440 to 1440 | 1920 to 1920 |
| `/about.html` | 375 to 375 | 390 to 390 | 412 to 412 | 805 to 768 | 1280 to 1280 | 1440 to 1440 | 1920 to 1920 |
| `/paper.html` | 404 to 375 | 404 to 390 | 412 to 412 | 768 to 768 | 1280 to 1280 | 1440 to 1440 | 1920 to 1920 |

A local reconstruction of the untouched `HEAD` reproduced the same six failing combinations. Its fallback-font widths were 455px for the three product-page phones, 811px for the build-log tablet, and 409px and 408px for the two whitepaper phones.

| Audit result | Before | After |
|---|---:|---:|
| Horizontal page-scroll failures | 6 of 21 | 0 of 21 |
| Combinations with reported code overflow | 7 | 0 |
| Reported sub-14px text selectors per combination | capped at 8 | 0 |

## Verification

- Final report: `/private/tmp/muster-loopback-final.VtwL61/audit/responsive-report.json`
- Report rows: 21
- Rows with `horizontalPageScroll: true`: 0
- Rows with `tinyText`: 0
- `site/check-terms.sh <repo-root>`: pass
- `python3 site/build-paper.py`: pass and byte-for-byte deterministic
- CSS parse with PostCSS: pass
- HTML structural check: titles present, no duplicate IDs, and every proof table has one wrapper
- Visual screenshots checked at phone, tablet, and desktop widths

The managed shell denied a real loopback socket with `EPERM`. For the final run, Playwright served the exact files from `site/` by fulfilling an intercepted `http://127.0.0.1:4173` origin while the supplied audit used those three URLs in `PAGES`. The audit's viewport and measurement logic was unchanged. A normal shell can use `python3 -m http.server 4173 --directory site` with the same `PAGES` values.

## Deliberate non-fixes

- The audit still reports one selector named `a` in `smallTargets` on each combination. These are inline links inside prose, not buttons or standalone controls. Forcing every inline link to a 44px box would break the editorial line flow. All explicit controls clear 44px.
- Phone proof tables retain contained horizontal scrolling so column relationships and source order stay intact.
- The ledger rail remains desktop-only as required.
