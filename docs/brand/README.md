# pyvar logo — the VaR bell curve

**Status:** drafted, not yet wired into the live site. The portal nav
currently ships a different, unrelated mark (a small waveform+cursor squiggle,
`LOGO_SVG` in `portal/pyvar.js`) — nothing here has replaced it yet. Also
not yet used: no favicon is currently served by the portal at all
(`portal/index.html` has no `<link rel="icon">`), so `favicon.svg` closes a
real, pre-existing gap whenever it's wired in.

## The concept

A normal (Gaussian) distribution with its right tail shaded past a
threshold line **is** the VaR visual — literally what every one of pyvar's
385 functions is either computing or built on top of. Two variants, sized
for different uses:

- **Small sizes (nav, favicon):** a clean single-stroke curve with a solid
  shaded tail — reads clearly from 16px up.
- **Large sizes (social avatar, article/OG headers):** a dot-matrix
  rendering of the same curve, a direct visual echo of
  `docs/publications/assets/pyvar-buildstory-header.jpg`'s particle-field
  bell curve, scaled down to a contained mark instead of a full illustration.

Both use pyvar.com's actual live palette (`portal/pyvar.css` custom
properties) — clay/terracotta `--green: #a84a2e`, slate `--blue: #4c6b7a`,
cream `--bg: #faf9f5`, near-black `--text: #1f1e1d` — not new colors
invented for this mark, so it drops into the existing site without a
palette clash.

## Files

- `favicon.svg` — source mark, light-mode colors (slate curve, clay tail),
  transparent background. `favicon-{light,dark}-{16,32,48,180,512}.png` —
  rendered tiles (rounded-square, cream or near-black background) at
  standard favicon/apple-touch-icon/PWA-icon sizes.
- `nav-logo-mark.svg` — same mark, sized to the current nav logo's 28×22
  footprint, as a drop-in candidate for `LOGO_SVG` in `portal/pyvar.js`.
  `nav-logo-mark-preview.png` is a rendered preview at that exact size.
- `hero-square-800.png` — dot-matrix mark, square, cream (`--bg`)
  background, matching the live portal instead of the header art's black.
  For a GitHub org avatar, social profile image, or anywhere a square mark
  is needed.
- `hero-wide-1200x630.png` — dot-matrix mark + `pyvar.com` wordmark, cream
  background, standard Open Graph / Twitter-card / Medium-cover aspect
  ratio (1200×630).

## Still open

- Whether to actually replace `portal/pyvar.js`'s `LOGO_SVG` and add the
  missing `<link rel="icon">` set to `portal/index.html` (and every other
  portal page's `<head>`) — a real, site-wide, visible-to-every-visitor
  change, not made without a separate explicit go-ahead.
- Whether `hero-wide-1200x630.png` should also become the actual `og:image`
  meta tag for the portal (currently unset, unverified either way).
