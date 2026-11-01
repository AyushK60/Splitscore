/**
 * Rule-specific explanatory copy for the three explanation levels shown on a
 * finding: Quick explanation / More context / Technical details.
 *
 * Everything here is *concise editorial copy* layered on top of the finding
 * the backend actually produced. Counts, units, examples, assumptions and
 * limitations always come from the finding itself — never from this file — so
 * the numbers stay exactly as the engine counted them.
 *
 * Accuracy rules baked into the copy:
 *   - near duplicates are similarity candidates, never confirmed copies;
 *   - no sentence here claims a dataset is safe or a model is accurate;
 *   - each mechanism paragraph explains how the sharing can flatter results,
 *     not that it definitely did.
 */

import type { AuditConfig } from '../api/types'

/**
 * The three explanation levels. The selection is shared across every finding so
 * that choosing "Technical details" once keeps that level while the reader
 * expands other findings or moves between results and comparison screens.
 */
export type ExplanationLevel = 'quick' | 'context' | 'technical'

let persistedLevel: ExplanationLevel = 'quick'

export function getPersistedLevel(): ExplanationLevel {
  return persistedLevel
}

export function persistLevel(level: ExplanationLevel): void {
  persistedLevel = level
}

/** Test helper: every screen starts a fresh session at the quick level. */
export function resetExplanationLevel(): void {
  persistedLevel = 'quick'
}

/** The five audited rules; unknown ids fall back to `genericMechanism`. */
export type KnownRuleId =
  | 'SS-ENT-001'
  | 'SS-DUP-001'
  | 'SS-CHR-001'
  | 'SS-TGT-001'
  | 'SS-NEAR-001'

/**
 * "More context" — how the sharing happens, in everyday language.
 * One paragraph per rule; deliberately mechanism-only (no counts: the finding
 * supplies those).
 */
const MECHANISM: Record<KnownRuleId, string> = {
  'SS-ENT-001':
    'Rows for the same person, customer or device landed on both sides of the split. ' +
    'The model trains on some of their rows and is then tested on others, so it can score well ' +
    'by recognising entities it has already seen rather than by generalising to ones it has not.',
  'SS-DUP-001':
    'Rows with identical values across the compared features appear in both training and test. ' +
    'A model can answer the test rows by recalling the memorised training copies, which makes ' +
    'the measured result look better than performance on genuinely new records.',
  'SS-CHR-001':
    'Some training rows are newer than the earliest test timestamp, so fitting could use ' +
    'information from after the moment being predicted. For problems that forecast forward in ' +
    'time, that flatters the score compared with what deployment would see.',
  'SS-TGT-001':
    'A feature column reproduces the target so closely that a model can read the answer straight ' +
    'off that feature instead of learning from the real inputs. The test score then reflects that ' +
    'shortcut rather than useful prediction.',
  'SS-NEAR-001':
    'Rows on the two sides are very similar to each other. These are similarity candidates, not ' +
    'confirmed copies — but if they are genuinely near-duplicate records, the test rows are ' +
    'easier than they look.',
}

const genericMechanism =
  'The check found rows that cross the training/test boundary in a way that can share ' +
  'information between the two sides, which can make the test result look better than it ' +
  'would on data the model has never seen.'

/**
 * A short "why should I care" line used only if the backend did not supply a
 * severity rationale (it normally does).
 */
const genericWhyCare =
  'Sharing between training and test data can inflate the measured result, so it is worth checking before you trust the number.'

export function mechanismCopy(ruleId: string): string {
  return MECHANISM[ruleId as KnownRuleId] ?? genericMechanism
}

export function whyCareCopy(_ruleId: string): string {
  return genericWhyCare
}

/**
 * Technical-level note about checks that did not run. Kept here so every
 * finding's technical panel states the same honest boundary: not-evaluated is
 * reported separately and is never folded into findings.
 */
export const NOT_RUN_NOTE =
  'Checks that were skipped, disabled, unsupported or not evaluated are reported separately from ' +
  'findings and are never counted as findings.'

/**
 * Formats one finding count for the quick level, preserving the engine's unit
 * and denominator: "Shared entity values: 2 of 4 values".
 */
export function quickCountLine(count: {
  label: string
  affected: number
  denominator: number
  unit: string
}): string {
  const affected = count.affected.toLocaleString('en-US')
  if (count.denominator > 0) {
    return `${count.label}: ${affected} of ${count.denominator.toLocaleString('en-US')} ${count.unit}`
  }
  return `${count.label}: ${affected} ${count.unit}`
}

/**
 * Technical level: the audit settings that actually applied to this rule,
 * read from the run's own configuration. Values are rendered verbatim — no
 * interpretation is added here.
 */
export function settingsForRule(
  ruleId: string,
  config: AuditConfig,
): Array<{ label: string; value: string }> {
  const item = (label: string, value: string | number | boolean | string[]) => ({
    label,
    value: Array.isArray(value)
      ? value.length
        ? value.join(', ')
        : '(none)'
      : typeof value === 'boolean'
        ? value
          ? 'on'
          : 'off'
        : String(value),
  })
  const shared = [
    item('Strip whitespace', config.strip_whitespace),
    item('Normalise numeric strings', config.normalize_numeric_strings),
    item('Missing-value tokens', config.missing_tokens),
    item('Max examples per finding', config.max_examples),
  ]
  switch (ruleId) {
    case 'SS-ENT-001':
      return [
        item('High-severity test share at or above', config.entity_overlap_high_test_share),
        ...shared,
      ]
    case 'SS-DUP-001':
      return shared
    case 'SS-CHR-001':
      return [
        item('Chronology intent', config.chronology_intent),
        item('High-severity train share at or above', config.chronology_high_train_share),
        ...shared,
      ]
    case 'SS-TGT-001':
      return [
        item('Min coverage', config.target_copy_min_coverage),
        item('High coverage at or above', config.target_copy_high_coverage),
        item('Baseline margin', config.target_copy_baseline_margin),
        item('Min comparable rows', config.target_copy_min_comparable_rows),
        ...shared,
      ]
    case 'SS-NEAR-001':
      return [
        item('Enabled', config.near_duplicates.enabled),
        item('Distance threshold at or below', config.near_duplicates.threshold),
        item('Scaling', config.near_duplicates.scaling),
        item('Min numeric column ratio', config.near_duplicates.min_numeric_ratio),
        item('Oversize policy', config.near_duplicates.oversize_policy),
        item('Max combined rows', config.near_duplicates.max_combined_rows),
        ...shared,
      ]
    default:
      return shared
  }
}
