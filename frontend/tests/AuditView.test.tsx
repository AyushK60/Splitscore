/**
 * AuditView presentation: findings vs checks that did not run stay distinct,
 * "Open in evidence view" selects the right finding, and the empty state for
 * zero findings is not conflated with not-evaluated checks.
 *
 * The API boundary is mocked; the provider and the view under test are real.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import { AppProvider, useApp } from '../src/state/AppState'
import { AuditView } from '../src/views/AuditView'
import type { ViewId } from '../src/lib/router'
import {
  auditResponseFixture,
  checksFixture,
  demosFixture,
  healthFixture,
  loadedFixture,
  previewFixture,
} from './fixtures'

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClient>()
  return {
    ...actual,
    api: {
      health: vi.fn(),
      checks: vi.fn(),
      demos: vi.fn(),
      loadDemo: vi.fn(),
      uploadDataset: vi.fn(),
      dataset: vi.fn(),
      preview: vi.fn(),
      validateRoles: vi.fn(),
      columnValues: vi.fn(),
      audit: vi.fn(),
      compare: vi.fn(),
    },
    downloadExport: vi.fn(),
  }
})

const store: { ctx: ReturnType<typeof useApp> | null } = { ctx: null }

function Probe({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  store.ctx = useApp()
  return <AuditView onNavigate={onNavigate} />
}

async function renderAuditView(audit = auditResponseFixture()) {
  vi.mocked(api.health).mockResolvedValue(healthFixture())
  vi.mocked(api.checks).mockResolvedValue(checksFixture())
  vi.mocked(api.demos).mockResolvedValue(demosFixture())
  vi.mocked(api.loadDemo).mockResolvedValue(loadedFixture())
  vi.mocked(api.audit).mockResolvedValue(audit)
  vi.mocked(api.preview).mockResolvedValue(previewFixture())

  const onNavigate = vi.fn()
  render(
    <AppProvider>
      <Probe onNavigate={onNavigate} />
    </AppProvider>,
  )
  await screen.findByText('No audit has been run in this session')
  await act(async () => {
    await store.ctx?.loadDemo('fixture_demo')
  })
  await act(async () => {
    await store.ctx?.runAudit()
  })
  return { onNavigate }
}

beforeEach(() => {
  store.ctx = null
})

describe('findings and checks that did not run', () => {
  it('renders findings and keeps not-evaluated checks in their own section', async () => {
    await renderAuditView()

    // The finding itself, with its evidence summary (the title also appears in
    // the rule filter and the outcome table, hence getAllByText).
    expect(
      screen.getAllByText('Entity overlap between train and test splits').length,
    ).toBeGreaterThan(0)
    expect(screen.getByText(/2 entity value\(s\) are shared/)).toBeInTheDocument()

    // The check that did not run is presented separately, with the reason,
    // and explicitly flagged as not passing.
    expect(screen.getByText(/Checks that did not run \(1\)/)).toBeInTheDocument()
    expect(
      screen.getAllByText('Training records extend beyond the earliest test timestamp').length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByText('No timestamp column was selected.').length).toBeGreaterThan(0)
    expect(screen.getByText('These are not passing results')).toBeInTheDocument()
  })

  it('"Open in evidence view" selects the finding that was opened', async () => {
    const { onNavigate } = await renderAuditView()

    fireEvent.click(screen.getByRole('button', { name: /Entity overlap between train and test splits/ }))
    fireEvent.click(screen.getByRole('button', { name: /Open in evidence view/ }))

    const selected = store.ctx?.selectedFinding
    expect(selected?.finding.rule_id).toBe('SS-ENT-001')
    expect(selected?.origin).toBe('audit')
    expect(selected?.contextLabel).toBeTruthy()
    expect(onNavigate).toHaveBeenCalledWith('evidence')
  })

  it('shows a no-findings empty state distinct from not-evaluated checks', async () => {
    const clean = auditResponseFixture()
    const noFindings = {
      ...clean,
      result: {
        ...clean.result,
        findings: [],
        evaluation: {
          ...clean.result.evaluation,
          findings_total: 0,
          findings_by_severity: { high: 0, medium: 0, low: 0, info: 0 },
          headline: '0 findings across 1 evaluated check',
        },
        rule_outcomes: clean.result.rule_outcomes.map((outcome) =>
          outcome.rule_id === 'SS-ENT-001' ? { ...outcome, findings: [] } : outcome,
        ),
      },
    }
    await renderAuditView(noFindings)

    // "No findings" is about the evaluated checks only…
    expect(screen.getByText('No findings')).toBeInTheDocument()
    expect(screen.getByText(/The enabled checks found no supported issue/)).toBeInTheDocument()
    // …while the check that did not run is still listed as not passing.
    expect(screen.getByText(/Checks that did not run \(1\)/)).toBeInTheDocument()
    expect(screen.getByText('These are not passing results')).toBeInTheDocument()
  })
})
