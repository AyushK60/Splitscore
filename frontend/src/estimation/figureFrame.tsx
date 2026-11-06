/**
 * Shared figure chrome for the Effect Estimation Studio.
 *
 * Every analytical view renders exactly one large figure inside this frame. The
 * frame owns the title, the method line, the legend slot, the export toolbar and
 * the scientific footnote; the view owns the geometry. Exports always serialise
 * the live SVG, so a figure cannot drift from the numbers it was drawn from.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'

import {
  exportFigureCsv,
  exportFigureJson,
  exportFigurePng,
  exportFigureSvg,
  type FigureExportMeta,
} from './estimationExport'

/**
 * Width of a block element, measured with ResizeObserver where available.
 *
 * jsdom has no ResizeObserver; the fallback keeps charts renderable in tests at
 * a fixed width and still responds to window resizes, so no figure disappears
 * just because the browser lacks the observer.
 */
export function useMeasuredWidth(ref: RefObject<HTMLElement | null>, fallback = 900): number {
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => {
      const next = element.getBoundingClientRect().width
      if (next > 0) setWidth(Math.round(next))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, fallback])
  return width
}

export function FigureFrame({
  eyebrow,
  title,
  description,
  svgRef,
  exportMeta,
  legend,
  footnote,
  aside,
  children,
  testId,
}: {
  eyebrow: string
  title: ReactNode
  description?: ReactNode
  svgRef: RefObject<SVGSVGElement | null>
  exportMeta: FigureExportMeta
  legend?: ReactNode
  footnote?: ReactNode
  aside?: ReactNode
  children: ReactNode
  testId?: string
}) {
  const [exportError, setExportError] = useState<string | null>(null)
  const [exported, setExported] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  const announce = useCallback((message: string) => {
    setExported(message)
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setExported(null), 4000)
  }, [])

  const onPng = useCallback(() => {
    setExportError(null)
    exportFigurePng(svgRef.current, exportMeta)
      .then((ok) => announce(ok ? 'PNG figure downloaded.' : 'The figure is not rendered yet.'))
      .catch((error: unknown) =>
        setExportError(error instanceof Error ? error.message : 'PNG export failed.'),
      )
  }, [announce, exportMeta, svgRef])

  return (
    <section className="estfig" aria-label={typeof title === 'string' ? title : undefined} data-testid={testId}>
      <header className="estfig__head">
        <div className="estfig__heading">
          <p className="estfig__eyebrow">{eyebrow}</p>
          <h2 className="estfig__title">{title}</h2>
          {description ? <p className="estfig__desc">{description}</p> : null}
        </div>
        {aside ? <div className="estfig__aside">{aside}</div> : null}
        <div className="estfig__exports" role="group" aria-label="Figure export">
          <span className="estfig__exportlabel">Export</span>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => {
              setExportError(null)
              if (exportFigureSvg(svgRef.current, exportMeta)) announce('SVG figure downloaded.')
              else setExportError('The figure is not rendered yet.')
            }}
            title="Vector figure with a caption block, suitable for publication"
          >
            SVG
          </button>
          <button type="button" className="btn btn--small" onClick={onPng} title="2× PNG for slides and reports">
            PNG
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => {
              exportFigureCsv(exportMeta)
              announce('Plotted values downloaded as CSV.')
            }}
            title="Exactly the values plotted in this figure"
          >
            CSV
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => {
              exportFigureJson(exportMeta)
              announce('Figure metadata downloaded as JSON.')
            }}
            title="Figure metadata: run, estimator, cohort and plotted values"
          >
            JSON
          </button>
        </div>
      </header>
      {legend ? <div className="estfig__legend">{legend}</div> : null}
      <div className="estfig__plot">{children}</div>
      {exportError ? (
        <p className="estfig__error" role="alert">
          {exportError}
        </p>
      ) : null}
      <p className="visually-hidden" role="status" aria-live="polite">
        {exported ?? ''}
      </p>
      {footnote ? <div className="estfig__foot">{footnote}</div> : null}
    </section>
  )
}

/** A legend swatch + label, used by the summary, balance and overlap figures. */
export function LegendItem({
  variant,
  children,
}: {
  variant: string
  children: ReactNode
}) {
  return (
    <span className="estlegend__item">
      <span className={`estlegend__swatch estlegend__swatch--${variant}`} aria-hidden="true" />
      {children}
    </span>
  )
}
