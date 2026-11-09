import { useCallback, useEffect, useState } from 'react'

/**
 * The hero's narrative clock.
 *
 * Four phases, each advanced by a timer rather than a per-frame render loop:
 * the scene itself is CSS-driven, so a phase change is one class flip and the
 * browser does the interpolation. That keeps the hero off the main thread and
 * makes pause a matter of freezing CSS animation rather than a JS loop.
 *
 * The sequence is honest about itself: it illustrates *what a boundary audit
 * asks*, and the readout next to it says so. Nothing here is a computed result.
 */
export type HeroPhase = 'forming' | 'scanning' | 'discovery' | 'evidence'

export type HeroPhaseMeta = {
  id: HeroPhase
  short: string
  title: string
  body: string
  hint: string
}

export const HERO_PHASES: HeroPhaseMeta[] = [
  {
    id: 'forming',
    short: 'Registers',
    title: 'Two registers, one source table',
    body: 'Training and testing records arrive as separate plates. The boundary between them is the only thing that makes an evaluation independent - and nothing has crossed it yet.',
    hint: 'Watch where the plates land: left of the rule is training, right of it is testing.',
  },
  {
    id: 'scanning',
    short: 'Boundary',
    title: 'Verifying the boundary',
    body: 'The instrument inspects every training plate for information that also exists on the testing side. Most plates carry no shared identity, and the scan moves past them.',
    hint: 'A clean scan is not a pass: it reports only what these checks can see.',
  },
  {
    id: 'discovery',
    short: 'Discovery',
    title: 'Context crosses the rule',
    body: 'One training plate and one testing plate resolve to the same customer. The model can recognise a record it will be scored on, so the test score stops measuring generalisation.',
    hint: 'The pair is a relationship between records - not a model result.',
  },
  {
    id: 'evidence',
    short: 'Evidence',
    title: 'The rows behind the finding',
    body: 'SplitScope reports the identifiers and the values that matched, so the claim can be checked by hand instead of trusted as a score.',
    hint: 'Every finding carries its denominators and the rows that produced it.',
  },
]

const DURATION: Record<HeroPhase, number> = {
  forming: 3400,
  scanning: 3400,
  discovery: 3900,
  evidence: 4800,
}

const NEXT: Record<HeroPhase, HeroPhase> = {
  forming: 'scanning',
  scanning: 'discovery',
  discovery: 'evidence',
  evidence: 'forming',
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduced
}

export function useHeroSequence() {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<HeroPhase>(() => (prefersReducedMotion() ? 'evidence' : 'forming'))
  const [playing, setPlaying] = useState(() => !prefersReducedMotion())
  const [cycle, setCycle] = useState(0)

  useEffect(() => {
    if (!reducedMotion) return
    setPhase('evidence')
    setPlaying(false)
  }, [reducedMotion])

  useEffect(() => {
    if (reducedMotion || !playing) return
    const timer = window.setTimeout(() => setPhase(NEXT[phase]), DURATION[phase])
    return () => window.clearTimeout(timer)
  }, [phase, playing, reducedMotion])

  const toggle = useCallback(() => {
    if (reducedMotion) return
    setPlaying((value) => !value)
  }, [reducedMotion])

  const replay = useCallback(() => {
    if (reducedMotion) return
    setCycle((value) => value + 1)
    setPhase('forming')
    setPlaying(true)
  }, [reducedMotion])

  const jump = useCallback((next: HeroPhase) => {
    setPhase(next)
    setPlaying(false)
  }, [])

  const inspect = useCallback(() => {
    setPhase('evidence')
    setPlaying(false)
  }, [])

  return { phase, playing, cycle, reducedMotion, toggle, replay, jump, inspect }
}
