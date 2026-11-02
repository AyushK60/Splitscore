import { useEffect, type RefObject } from 'react'

/**
 * Reveals every `[data-reveal]` element inside `root` the first time it enters
 * the viewport. Elements start at `data-reveal=""` (hidden by CSS) and are
 * switched to `data-reveal="in"` once, then unobserved.
 *
 * Under `prefers-reduced-motion` — or without IntersectionObserver — every
 * element is revealed immediately, so content is never hidden from a user who
 * opted out of motion or from a browser that cannot observe scroll.
 */
export function useRevealOnScroll<T extends HTMLElement>(rootRef: RefObject<T | null>) {
  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    const items = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'))
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

    if (reduced || typeof IntersectionObserver === 'undefined') {
      for (const item of items) item.dataset.reveal = 'in'
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          ;(entry.target as HTMLElement).dataset.reveal = 'in'
          observer.unobserve(entry.target)
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    )

    for (const item of items) observer.observe(item)
    return () => observer.disconnect()
  }, [rootRef])
}
