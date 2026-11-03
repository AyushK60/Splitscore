import { useCallback, useEffect, useState } from 'react'

export type ViewId =
  | 'home'
  | 'overview'
  | 'dataset'
  | 'study'
  | 'explore'
  | 'audit'
  | 'models'
  | 'evidence'
  | 'comparison'
  | 'export'

const KNOWN: ViewId[] = [
  'home',
  'overview',
  'dataset',
  'study',
  'explore',
  'audit',
  'models',
  'evidence',
  'comparison',
  'export',
]

export function isViewId(value: string): value is ViewId {
  return (KNOWN as string[]).includes(value)
}

/**
 * Hash routing: deep links work, the browser back button works, and no router
 * dependency is needed for seven views.
 *
 * Only hashes of the form `#/view` change the route. Anything else (`#main`
 * from the skip link, `#method` from an in-page anchor) is a plain fragment
 * link and deliberately returns `null` so the current view is kept — otherwise
 * skipping to content would bounce the user back to the landing page.
 *
 * An empty hash is the product front door: the landing page.
 */
function routeFromHash(): ViewId | null {
  const hash = window.location.hash
  if (hash === '' || hash === '#') return 'home'
  const match = /^#\/([A-Za-z-]+)/.exec(hash)
  if (match && isViewId(match[1])) return match[1]
  return null
}

export function useHashRoute(): [ViewId, (view: ViewId) => void] {
  const [view, setView] = useState<ViewId>(() => routeFromHash() ?? 'home')

  useEffect(() => {
    const onChange = () => {
      const next = routeFromHash()
      if (next) setView(next)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((next: ViewId) => {
    if (window.location.hash === `#/${next}`) {
      setView(next)
      return
    }
    window.location.hash = `#/${next}`
  }, [])

  return [view, navigate]
}