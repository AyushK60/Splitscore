---
name: premium-scientific-ui
description: Design and implement an exceptional, uncluttered, responsive scientific software landing page and cohesive SplitScope interior without compromising functionality.
metadata:
  category: frontend-design
  project: splitscope-v2
---

# Premium scientific UI — SplitScope V2

Use for S1 landing page and S2 interior design. This is an implementation skill, not permission to replace functioning auditing logic.

## Design brief
- Visual character: Scientific Observatory + Precision Engineering + premium editorial clarity. Distinctive, not a generic SaaS dashboard.
- **One large visual focus per screen.** The reference image identifies scientific chart *types*, NOT a six-panel composition. Never place DAG, parallel coordinates, regression results and diagnostics together in a hero or cramped screen.
- Landing: bold typographic hierarchy, compelling scientifically grounded headline, two working primary actions (demo and enter application), original animated SVG/data-flow visual. The visual may be conceptual, but must never falsely suggest real computed analysis.
- Spacious rhythm: broad margins, deliberate grid, generous whitespace, clear typographic scale, quiet dividers, restrained highlight colors. Use navy/slate, ivory/off-white, teal/cyan accents with legible contrast; don't create a glowing cyberpunk collage.
- Establish a common token system for colors, spacing, radii, font sizes, shadows and motion and apply it across landing and existing application shell.
- Interior: prioritize the current job. Use a single dominant main canvas or report area with small optional controls; advanced details through tabs, drawers or expanders. Avoid dashboard overload.
- The eventual causal DAG, parallel-coordinates view and model diagnostics belong in separate workspaces; do **not** implement decorative fake versions now.

## Motion and interaction
- Animation must communicate an actual flow or relationship; avoid random particles, looping typewriter effects or continuous high-energy movement.
- Favor performant SVG/CSS transforms/opacity. Support `prefers-reduced-motion: reduce` and keep layout stable.
- Buttons and navigation must work; no dead placeholder CTAs. Future capabilities must be labelled planned or not linked.
- Keyboard focus, contrast, semantic structure, discernible labels and text alternatives are part of polish.

## Implementation workflow
1. Inspect current React/Vite files and existing navigation, CSS and UI contracts. Prefer incremental component changes over rewriting state and API clients.
2. Write a small visual plan: section order, token palette, animation storyboard and mobile layout. Then implement actual code.
3. Verify desktop (about 1440px), tablet (about 768px), mobile (about 390px). No horizontal overflow, cropped labels or lost actions.
4. Verify core existing journeys: demo -> dataset -> audit -> evidence -> comparison -> export. UI refactoring must not change numerical findings.
5. Capture genuine before/after screenshots if supported; visually inspect for clutter and consistency. Report exact checks run and remaining issues.

## Quality bar
- A professional first fold with **one hero illustration** and striking design, not a template composed of six feature cards.
- No fake metrics, fabricated model results or visually impressive but misleading analysis.
- Production build passes and no known regressions. If short of time, finish one polished coherent section rather than leave multiple broken partial sections.
