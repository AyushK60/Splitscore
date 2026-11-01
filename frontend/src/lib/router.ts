import { useCallback, useEffect, useState } from 'react'

export type ViewId =
  | 'overview'
  | 'dataset'
  | 'audit'
  | 'evidence'
  | 'comparison'
  | 'export'

const KNOWN: ViewId[] = ['overview', 'dataset', 'audit', 'evidence', 'comparison', 'export']

export function isViewId(value: string): value is ViewId {
  return (KNOWN as string[]).includes(value)
}

function currentView(): ViewId {
  const raw = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  return isViewId(raw) ? raw : 'overview'
}

/**
 * Hash-based routing: deep links work, the browser back button works, and no
 * router dependency is needed for six views.
 */
export function useHashRoute(): [ViewId, (view: ViewId) => void] {
  const [view, setView] = useState<ViewId>(() => currentView())

  useEffect(() => {
    const onChange = () => setView(currentView())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((next: ViewId) => {
    if (currentView() === next) {
      setView(next)
      return
    }
    window.location.hash = `#/${next}`
  }, [])

  return [view, navigate]
}
