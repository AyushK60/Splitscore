/**
 * Audit settings editor.
 *
 * Every threshold the engine uses is editable and is echoed back in the report, so
 * a finding can always be traced to the configuration that produced it. The
 * near-duplicate block is opt-in and states its own cost and limits inline.
 */

import type { AuditConfig } from '../api/types'
import { Callout } from './ui'

function Toggle({
  id,
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  id: string
  label: string
  hint?: string
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="checkbox-row">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id}>
        {label}
        {hint ? <span className="hint">{hint}</span> : null}
      </label>
    </div>
  )
}

function NumberField({
  id,
  label,
  hint,
  value,
  min,
  max,
  step,
  integer,
  onChange,
}: {
  id: string
  label: string
  hint?: string
  value: number
  min?: number
  max?: number
  step?: number
  integer?: boolean
  onChange: (value: number) => void
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        value={Number.isFinite(value) ? value : ''}
        min={min}
        max={max}
        step={step ?? (integer ? 1 : 0.01)}
        onChange={(event) => {
          const parsed = integer ? Number.parseInt(event.target.value, 10) : Number(event.target.value)
          if (Number.isNaN(parsed)) return
          onChange(parsed)
        }}
      />
      {hint ? <span className="hint">{hint}</span> : null}
    </div>
  )
}

export function AuditConfigEditor({
  config,
  onChange,
  hasTarget,
  hasEntity,
  hasTimestamp,
  numericFeatureRatio,
}: {
  config: AuditConfig
  onChange: (config: AuditConfig) => void
  hasTarget: boolean
  hasEntity: boolean
  hasTimestamp: boolean
  numericFeatureRatio: number | null
}) {
  function patch(next: Partial<AuditConfig>) {
    onChange({ ...config, ...next })
  }

  function patchNear(next: Partial<AuditConfig['near_duplicates']>) {
    onChange({ ...config, near_duplicates: { ...config.near_duplicates, ...next } })
  }

  return (
    <div className="stack">
      <fieldset>
        <legend>Checks</legend>
        <Toggle
          id="cfg-exact"
          label="Exact feature duplicates across train and test"
          hint="Collision-safe: candidate groups are confirmed by comparing values, not just hashes."
          checked={config.enable_exact_duplicates}
          onChange={(value) => patch({ enable_exact_duplicates: value })}
        />
        <Toggle
          id="cfg-entity"
          label="Entity / group overlap"
          hint={
            hasEntity
              ? 'Runs against the selected entity column.'
              : 'Needs an entity column. Without one this check is reported as not evaluated.'
          }
          checked={config.enable_entity_overlap}
          onChange={(value) => patch({ enable_entity_overlap: value })}
        />
        <Toggle
          id="cfg-chronology"
          label="Chronology check"
          hint={
            hasTimestamp
              ? 'Compares the train and test timestamp ranges under the stated intent.'
              : 'Needs a timestamp column. Without one this check is reported as not evaluated.'
          }
          checked={config.enable_chronology}
          onChange={(value) => patch({ enable_chronology: value })}
        />
        <Toggle
          id="cfg-target-copy"
          label="Exact target-copy feature"
          hint={
            hasTarget
              ? 'Compares every selected feature against the target on comparable non-missing rows.'
              : 'Needs a target column. Without one this check is reported as not evaluated.'
          }
          checked={config.enable_target_copy}
          onChange={(value) => patch({ enable_target_copy: value })}
        />
        <Toggle
          id="cfg-near"
          label="Near-duplicate candidates (opt-in, bounded)"
          hint="Similarity is not proof of leakage. Read the definition and limits below before enabling."
          checked={config.near_duplicates.enabled}
          onChange={(value) => patchNear({ enabled: value })}
        />
      </fieldset>

      {config.near_duplicates.enabled ? (
        <fieldset>
          <legend>Near-duplicate settings</legend>
          <Callout tone="warn" title="What this check does and does not establish">
            <ul className="list-tight">
              <li>
                It standardises numeric features (robust scaling by default), computes a Euclidean
                distance, and reports cross-split pairs at or below the threshold as{' '}
                <em>candidates</em>.
              </li>
              <li>
                Similarity alone is not leakage. Near-identical rows can be legitimate and a distance
                below a threshold is not a proof of any relationship.
              </li>
              <li>
                Only numeric feature columns participate. Categorical and text features are ignored,
                and constant columns carry no distance information at all.
              </li>
              <li>
                The scaling is diagnostic only. It is never exported as a fitted modelling pipeline.
              </li>
            </ul>
          </Callout>
          <div className="row">
            <NumberField
              id="cfg-near-threshold"
              label="Distance threshold"
              hint="Scaled Euclidean distance; a pair at or below this is a candidate."
              value={config.near_duplicates.threshold}
              min={0}
              max={4}
              step={0.005}
              onChange={(value) => patchNear({ threshold: value })}
            />
            <div className="field">
              <label htmlFor="cfg-near-scaling">Scaling</label>
              <select
                id="cfg-near-scaling"
                value={config.near_duplicates.scaling}
                onChange={(event) =>
                  patchNear({ scaling: event.target.value as 'robust' | 'none' })
                }
              >
                <option value="robust">Robust (median / IQR)</option>
                <option value="none">None — raw units</option>
              </select>
              <span className="hint">
                Robust scaling divides by the interquartile range, so one outlier cannot dominate.
              </span>
            </div>
            <NumberField
              id="cfg-near-rows"
              label="Max combined rows"
              hint="Above this, the check follows the oversize policy rather than running unbounded."
              value={config.near_duplicates.max_combined_rows}
              min={10}
              max={5000}
              step={10}
              integer
              onChange={(value) => patchNear({ max_combined_rows: value })}
            />
            <NumberField
              id="cfg-near-seed"
              label="Sampling seed"
              hint="Used only when the oversize policy samples. The sampled scope is named in the output."
              value={config.near_duplicates.sample_seed}
              min={0}
              step={1}
              integer
              onChange={(value) => patchNear({ sample_seed: value })}
            />
            <div className="field">
              <label htmlFor="cfg-near-policy">If over the row budget</label>
              <select
                id="cfg-near-policy"
                value={config.near_duplicates.oversize_policy}
                onChange={(event) =>
                  patchNear({ oversize_policy: event.target.value as 'sample' | 'skip' })
                }
              >
                <option value="sample">Sample deterministically (seeded)</option>
                <option value="skip">Skip and report as not evaluated</option>
              </select>
            </div>
            <NumberField
              id="cfg-near-missing"
              label="Max missing fraction per row"
              hint="Rows with more missing numeric features than this are excluded from the distance."
              value={config.near_duplicates.max_missing_fraction_per_row}
              min={0}
              max={1}
              step={0.05}
              onChange={(value) => patchNear({ max_missing_fraction_per_row: value })}
            />
            <NumberField
              id="cfg-near-numeric"
              label="Min numeric share of features"
              hint="The check is skipped if fewer than this share of selected features are numeric."
              value={config.near_duplicates.min_numeric_ratio}
              min={0}
              max={1}
              step={0.05}
              onChange={(value) => patchNear({ min_numeric_ratio: value })}
            />
          </div>
          {numericFeatureRatio !== null ? (
            <p className="small muted" style={{ marginBottom: 0 }}>
              Currently {Math.round(numericFeatureRatio * 100)}% of the selected features are numeric.
              {numericFeatureRatio < config.near_duplicates.min_numeric_ratio
                ? ' That is below the minimum, so this check will report as not evaluated.'
                : ''}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      <details className="disclosure">
        <summary>Canonicalization and comparison rules</summary>
        <div className="stack" style={{ marginTop: 8 }}>
          <Toggle
            id="cfg-strip"
            label="Trim surrounding whitespace before comparing"
            hint="Applied to text feature values and to role labels. The stored dataset is not modified."
            checked={config.strip_whitespace}
            onChange={(value) => patch({ strip_whitespace: value })}
          />
          <Toggle
            id="cfg-numeric-strings"
            label="Treat numerically equal strings as equal"
            hint="Off by default. When on, '1.0' and '1' compare equal, which can merge genuinely distinct codes."
            checked={config.normalize_numeric_strings}
            onChange={(value) => patch({ normalize_numeric_strings: value })}
          />
          <div className="field">
            <label htmlFor="cfg-missing-tokens">Additional missing-value tokens</label>
            <input
              id="cfg-missing-tokens"
              type="text"
              value={config.missing_tokens.join(', ')}
              placeholder="e.g. NA, N/A, unknown"
              onChange={(event) =>
                patch({
                  missing_tokens: event.target.value
                    .split(',')
                    .map((token) => token.trim())
                    .filter(Boolean),
                })
              }
            />
            <span className="hint">
              Empty cells are always missing. Literal strings are values unless listed here, so a
              dataset that uses “NA” to mean “North America” is not corrupted by default.
            </span>
          </div>
          <NumberField
            id="cfg-max-examples"
            label="Maximum examples per finding"
            hint="Bounds the evidence attached to each finding. Counts remain dataset-wide."
            value={config.max_examples}
            min={1}
            max={50}
            integer
            onChange={(value) => patch({ max_examples: value })}
          />
          <NumberField
            id="cfg-max-example-rows"
            label="Maximum row ids per example"
            value={config.max_example_rows_per_example}
            min={1}
            max={20}
            integer
            onChange={(value) => patch({ max_example_rows_per_example: value })}
          />
        </div>
      </details>

      <details className="disclosure">
        <summary>Severity thresholds</summary>
        <p className="small muted">
          These control how a rule rates what it observed. They do not change what is detected, only
          how prominently it is reported. The rationale for each rating is printed with the finding.
        </p>
        <div className="row">
          <NumberField
            id="cfg-entity-share"
            label="Entity overlap: high severity above"
            hint="Share of test rows whose entity also appears in train."
            value={config.entity_overlap_high_test_share}
            min={0}
            max={1}
            step={0.01}
            onChange={(value) => patch({ entity_overlap_high_test_share: value })}
          />
          <NumberField
            id="cfg-chrono-share"
            label="Chronology: high severity above"
            hint="Share of train rows dated after the earliest test timestamp."
            value={config.chronology_high_train_share}
            min={0}
            max={1}
            step={0.005}
            onChange={(value) => patch({ chronology_high_train_share: value })}
          />
          <NumberField
            id="cfg-target-min"
            label="Target copy: report above"
            hint="Minimum share of comparable rows where the feature equals the target."
            value={config.target_copy_min_coverage}
            min={0}
            max={1}
            step={0.01}
            onChange={(value) => patch({ target_copy_min_coverage: value })}
          />
          <NumberField
            id="cfg-target-high"
            label="Target copy: high severity above"
            value={config.target_copy_high_coverage}
            min={0}
            max={1}
            step={0.01}
            onChange={(value) => patch({ target_copy_high_coverage: value })}
          />
          <NumberField
            id="cfg-target-margin"
            label="Target copy: margin over baseline"
            hint="How far the feature must beat the best constant guess before it is called a proxy."
            value={config.target_copy_baseline_margin}
            min={0}
            max={1}
            step={0.01}
            onChange={(value) => patch({ target_copy_baseline_margin: value })}
          />
          <NumberField
            id="cfg-target-min-rows"
            label="Target copy: minimum comparable rows"
            value={config.target_copy_min_comparable_rows}
            min={2}
            step={1}
            integer
            onChange={(value) => patch({ target_copy_min_comparable_rows: value })}
          />
        </div>
        <div className="field">
          <label htmlFor="cfg-chrono-intent">Chronology intent</label>
          <select
            id="cfg-chrono-intent"
            value={config.chronology_intent}
            onChange={(event) =>
              patch({
                chronology_intent: event.target.value as 'future_prediction' | 'not_applicable',
              })
            }
          >
            <option value="future_prediction">Future prediction (train must precede test)</option>
            <option value="not_applicable">
              Not applicable (a random split is intentional for this task)
            </option>
          </select>
          <span className="hint">
            The chronology check is only meaningful when the intended evaluation is future
            prediction. Choosing “not applicable” records that decision in the report.
          </span>
        </div>
      </details>
    </div>
  )
}
