import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type GlossaryTerm } from '../api'

let cached: Record<string, GlossaryTerm> | null = null
const subscribers = new Set<(g: Record<string, GlossaryTerm>) => void>()
let inFlight: Promise<void> | null = null

function fetchOnce() {
  if (inFlight) return inFlight
  inFlight = api.docs
    .glossary()
    .then((res) => {
      cached = res.terms
      subscribers.forEach((cb) => cb(res.terms))
    })
    .catch(() => {
      cached = {}
    })
  return inFlight
}

/** Merge backend glossary (formula + thresholds[].grade/range/min) with
 *  the locale's translated label, description, value descriptions, and
 *  threshold meanings. Backend remains the single source of truth for
 *  what terms exist; locale overrides are best-effort.
 */
export function useGlossary(): Record<string, GlossaryTerm> {
  const [terms, setTerms] = useState<Record<string, GlossaryTerm>>(cached ?? {})
  const { t, i18n } = useTranslation('glossary')

  useEffect(() => {
    if (cached) {
      setTerms(cached)
      return
    }
    subscribers.add(setTerms)
    fetchOnce()
    return () => {
      subscribers.delete(setTerms)
    }
  }, [])

  const localized: Record<string, GlossaryTerm> = {}
  for (const [key, raw] of Object.entries(terms)) {
    const localizedLabel = t(`terms.${key}.label`, { defaultValue: raw.label })
    const localizedDescription = t(`terms.${key}.description`, { defaultValue: raw.description })

    let localizedValues = raw.values
    if (raw.values) {
      localizedValues = {}
      for (const valueKey of Object.keys(raw.values)) {
        localizedValues[valueKey] = t(`terms.${key}.values.${valueKey}`, {
          defaultValue: raw.values[valueKey],
        })
      }
    }

    let localizedThresholds = raw.thresholds
    if (raw.thresholds) {
      localizedThresholds = raw.thresholds.map((thr) => {
        const slug =
          thr.grade ||
          thr.severity ||
          (thr.range ? thr.range.replace(/[^a-z]+/gi, '_').toLowerCase() : undefined)
        if (!slug) return thr
        const meaning =
          t(`terms.${key}.thresholds.${slug}`, { defaultValue: '' }) ||
          (thr.severity && t(`terms.${key}.thresholds.${thr.severity}`, { defaultValue: '' })) ||
          ''
        return {
          ...thr,
          label: thr.grade ? meaning || thr.label : thr.label,
          meaning: meaning || thr.meaning,
        }
      })
    }

    localized[key] = {
      ...raw,
      label: localizedLabel,
      description: localizedDescription,
      values: localizedValues,
      thresholds: localizedThresholds,
    }
  }

  // Re-key the result by language so consumers re-render on language change
  void i18n.language
  return localized
}
