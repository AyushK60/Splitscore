---
name: visual-regression-qa
description: Verify SplitScope V2 UI changes in a real browser with desktop/mobile screenshots, navigation and regression checks, plus transparent test evidence.
metadata:
  category: frontend-quality
  project: splitscope-v2
---

# Visual regression QA — SplitScope V2

Use after a landing-page or interior redesign, before declaring a milestone done.

## Real-browser acceptance loop
1. Determine the existing start commands from README/package.json; run app and inspect console, HTTP failures and obvious runtime errors. Do not invent evidence.
2. At minimum visit landing at desktop ~1440x900 and mobile ~390x844, plus one loaded dataset and an audit-results page. Save **actual** screenshots to `docs/screenshots/v2/` or report honestly why browser capture is unavailable.
3. Check that headings are readable, main CTA is visible and working, no horizontal scroll or overlapping elements, navigation is clear, states are not empty due to errors, motion respects reduced-motion, focus is visible.
4. Test the existing user journey: open bundled demo -> review data roles -> run audit -> open evidence -> compare split strategies -> export report. Record failing action, route and observed error.
5. Run the repository's existing frontend tests, lint, typecheck, build, relevant backend regression tests and E2E when available. Show command, pass/fail counts and whether any test was skipped; never claim tests were executed if they were not.
6. Compare UI to the design brief: premium, uncluttered and coherent from landing to interior. Reject placeholder charts, dead buttons, faux research numbers, stock dashboard collage and broken responsiveness.

## Reporting
Create or append to `docs/S0_S2_IMPLEMENTATION_REPORT.md` with screenshot paths, command results, reproducible defects and PASS/PARTIAL/BLOCKED. Preserve existing Git work. Do not force success if tooling is unavailable; state what could not be verified.
