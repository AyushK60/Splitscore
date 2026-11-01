import type { ReactNode } from 'react'

import type { CheckStatus, Severity } from '../api/types'
import { STATUS_EXPLANATION, severityLabel, statusLabel } from '../lib/format'

export function Card({
  title,
  actions,
  children,
  id,
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  id?: string
}) {
  return (
    <section className="card" id={id}>
      {(title || actions) && (
        <div className="row row--between card__head">
          <h2 className="card__title">{title}</h2>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function Badge({
  tone = 'neutral',
  children,
  title,
}: {
  tone?: 'neutral' | 'high' | 'medium' | 'low' | 'info' | 'ok'
  children: ReactNode
  title?: string
}) {
  return (
    <span className={`badge badge--${tone}`} title={title}>
      {children}
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={severity}>{severityLabel(severity)}</Badge>
}

/**
 * "Not evaluated" is deliberately a visually distinct state from "no findings".
 * A check that could not run must never read as a clean result.
 */
export function StatusBadge({ status }: { status: CheckStatus }) {
  let tone: 'ok' | 'medium' | 'neutral' | 'low' = 'low'
  if (status === 'disabled' || status === 'error' || status === 'not_evaluated' || status === 'insufficient_data' || status === 'unsupported') {
    tone = status === 'unsupported' ? 'neutral' : 'low'
  } else if (status === 'skipped') {
    tone = 'medium'
  } else {
    tone = 'ok'
  }
  return (
    <Badge tone={tone} title={STATUS_EXPLANATION[status]}>
      {statusLabel(status)}
    </Badge>
  )
}

export function Callout({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'danger' | 'ok' | 'synthetic'
  title?: ReactNode
  children: ReactNode
}) {
  return (
    <div className={`callout callout--${tone}`} role={tone === 'danger' ? 'alert' : undefined}>
      {title ? <p className="callout__title">{title}</p> : null}
      <div className="callout__body">{children}</div>
    </div>
  )
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
}) {
  return (
    <div className="stat">
      <p className="stat__label">{label}</p>
      <p className="stat__value">{value}</p>
      {hint ? <p className="stat__hint">{hint}</p> : null}
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {children ? <p className="muted">{children}</p> : null}
      {action ? <div className="empty__action">{action}</div> : null}
    </div>
  )
}

export function Spinner({ label = 'Working…' }: { label?: string }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </p>
  )
}

export function Table({
  caption,
  head,
  children,
}: {
  caption?: ReactNode
  head: ReactNode
  children: ReactNode
}) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table">
      <table className="table">
        {caption ? <caption className="table__caption">{caption}</caption> : null}
        <thead>{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function DefinitionList({ items }: { items: Array<{ term: string; value: ReactNode }> }) {
  return (
    <dl className="deflist">
      {items.map((item) => (
        <div key={item.term} className="deflist__row">
          <dt>{item.term}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
