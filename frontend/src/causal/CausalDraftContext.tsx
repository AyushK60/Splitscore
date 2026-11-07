import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { useReducer } from 'react'

import { causalLabReducer, initialLabState, type CausalLabState, type LabAction } from './CausalLabState'

/**
 * The unsaved causal draft outlives the Causal Lab route.
 *
 * The draft (nodes, edges, scope, assumptions, undo/redo) is scientific work the
 * user may have spent minutes on. Before S11 it lived in `useReducer` inside
 * `CausalLabView`, so navigating to any other stage unmounted the view and
 * silently discarded an uncommitted draft. The reducer itself is unchanged —
 * only its state now lives here, at the workbench level, so an ordinary
 * navigation preserves it exactly as it left it.
 *
 * `draftDatasetId` records which dataset the draft belongs to. The lab uses it
 * to distinguish "returning to my unsaved draft" from "switched dataset, the
 * draft is stale" — a dataset change resets the draft, because the scientific
 * context (observed columns) has genuinely changed.
 */
interface CausalDraftContextValue {
  state: CausalLabState
  dispatch: (action: LabAction) => void
  draftDatasetId: string | null
  setDraftDatasetId: (datasetId: string | null) => void
}

const CausalDraftContext = createContext<CausalDraftContextValue | null>(null)

export function CausalDraftProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(causalLabReducer, undefined, initialLabState)
  const [draftDatasetId, setDraftDatasetId] = useState<string | null>(null)
  const value = useMemo(
    () => ({ state, dispatch, draftDatasetId, setDraftDatasetId }),
    [state, draftDatasetId],
  )
  return <CausalDraftContext.Provider value={value}>{children}</CausalDraftContext.Provider>
}

export function useCausalDraft(): CausalDraftContextValue {
  const context = useContext(CausalDraftContext)
  if (context === null) {
    throw new Error('useCausalDraft must be used inside <CausalDraftProvider>')
  }
  return context
}
