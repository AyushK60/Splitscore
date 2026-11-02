# S3 visual refinement — the boundary observatory and calibrated identity

S3 keeps the forensic-archive identity approved after S2 and changes two things:
the hero becomes an instrument with a narrative, and the palette/typography are
calibrated for contrast instead of replaced.

## 1. The hero: "Information Boundary Observatory"

The previous hero was a full-bleed field with one perpetual filament. It read as
decoration because it had no beginning, middle or end. It is now a four-phase
sequence with a readout, a console and a labelled finding.

| Phase | What the scene does | What the readout says |
| --- | --- | --- |
| **A · Registers** | Twenty-one record plates draw into two registers with a staggered entrance. Column ticks render per plate; the split rule sits between them. | Two populations arrive as separate plates; nothing has crossed the rule. |
| **B · Boundary** | A scanner band crosses the training register; the aperture at the rule pulses; unrelated plates recede. | The instrument inspects every training plate for information that also exists on the testing side. |
| **C · Discovery** | One training plate and one testing plate rise and turn copper; the filament draws from one to the other; a copper bloom lights the crossing; the `SS-DUP-001` label appears with a leader. | The model can recognise a record it will be scored on, so the test score stops measuring generalisation. |
| **D · Evidence** | The rest of the field dims to 14%; the pair stays isolated; the readout lists the matched fields and the two row identifiers. | SplitScope reports the identifiers and values that matched, so the claim can be checked by hand. |

The loop then returns to A, so the whole story replays without a page reload.

### Controls and interaction

- **Pause / Play**, **Replay**, **Inspect pair**, and a four-step phase rail that
  jumps to any phase (all real `<button>`s, keyboard reachable, `aria-current`
  on the active phase, `aria-pressed` on inspect).
- The readout's phase title is an `aria-live="polite"` region, so the narrative
  is available without watching the animation.
- Clicking "Run this audit on the synthetic demo" in the readout loads the real
  bundled demo and lands on the dataset view — the same action as the hero CTA.
- `prefers-reduced-motion`: no timers, scanner hidden, and the scene renders the
  **evidence** frame as a complete still composition with the pair isolated.

### Composition decisions

- Two rows of larger plates instead of a dense grid: each record is legible at a
  glance, and the readout no longer sits on top of the test register.
- The finding label is drawn in the scene above the training register; the
  evidence detail lives in the readout, so the two never overlap the headline.
- On ≤700 px the observatory becomes a framed 320 px band below the readout
  rather than a background behind body copy, because a cropped background hid
  the instrument entirely on a phone.

## 2. Palette calibration

The identity is unchanged; the accents were re-tuned so focal points carry.

| Token | Before | S3 | Why |
| --- | --- | --- | --- |
| Copper | `#d9793f` | `#e07a3c` | slightly hotter so the finding reads as an event, not a tint |
| Copper light | `#eda06a` | `#f2a86f` | better contrast for the italic headline and pair ticks |
| Celadon | `#a7c4b2` | `#b4d0bd` | structure lines survive the JPEG/compression and low-brightness screens |
| Paper | `#ece3d2` | `#f3ebdb` | separates ivory bands from bone text; less archival grey |
| Paper (highlight) | `#f6efe2` | `#faf4e8` | raised cells and table headers |
| Celadon bright | — | `#d6ecdd` | scanner edge only, never text |

Semantics are unchanged and still enforced: **copper = something the audit
found**, celadon = structure, ink = the field, paper = specification. No new
accent colours were introduced, and buttons are not all orange.

## 3. Typography

- Headline scale is capped at 104 px (`clamp(42px, 6.9vw, 104px)`) so the two
  intended lines hold at 1440 px instead of wrapping to three when the readout
  column widened.
- Display serif remains for headlines; monospace remains for instrument labels,
  now at 10–11.5 px with 0.12–0.2 em tracking (previously some labels were
  smaller than that and read as texture rather than text).
- `text-wrap: pretty` on paragraphs and list items to stop single-word last
  lines in the narrow ledger columns.
- Body copy in the workspace uses the workbench's sans (not the display serif):
  analytical text stays readable, the serif stays editorial.

## 4. Concrete defects fixed

1. **Closing CTA crowding.** The final heading had a tight leading and no bottom
   margin, so its descenders ran into the paragraph. The copy column is now a
   flex stack: title `line-height: 0.98`, 26 px bottom margin, lede capped at
   44 ch with a 30 px gap before the buttons.
2. **Hero headline wrapping to three lines** after the readout column widened.
3. **Readout covering the test register.** Registers were reduced to two rows and
   the card starts below them; verified at 1440×900 and 1920×1080.
4. **Plates collapsing to the origin.** The entrance keyframes animated
   `transform`, which overrode each plate's SVG `translate` attribute. The
   animation now only animates opacity; position is untouched.
5. **Finding label over the headline.** Moved into the open area under the
   training register with a leader to the implicated plate.
6. **Mobile hero showed no instrument** (a slice crop behind an opaque scrim).
   Fixed by rendering the field as its own band under the readout.
7. **Empty evidence block reserved 100 px on mobile.** Hidden when not in the
   evidence phase.

## 5. Evidence

- `docs/screenshots/s3/s3-hero-forming.png`, `-scanning.png`, `-discovery.png`,
  `-evidence.png` — the four phases, 1440×900.
- `s3-hero-reduced-motion.png` — the still composition.
- `s3-landing-hero.png`, `s3-landing-desktop.png` (full page),
  `s3-landing-1920.png`, `s3-landing-tablet.png`, `s3-landing-mobile.png`.
- The capture script also asserts phase transitions, replay, autonomous advance,
  scanner hidden under reduced motion, 0 px overflow at 1440/1920/768/390 and a
  clean console (`frontend/scripts/capture-s3-screenshots.mjs`).

## 6. Limitations

- The scene is a fixed illustrative fixture, labelled as such in the plate, the
  index strip, the evidence caption and the readout. It is not a computed result
  and does not claim to be one.
- No audio, no WebGL, no animation library: one SVG, CSS transitions and four
  timers.
- The mobile band is a crop of the same viewBox; it is not a separate mobile
  composition with its own labels.
