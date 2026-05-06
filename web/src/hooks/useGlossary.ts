import { useEffect, useState } from 'react'
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

export function useGlossary(): Record<string, GlossaryTerm> {
  const [terms, setTerms] = useState<Record<string, GlossaryTerm>>(cached ?? {})

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

  return terms
}
