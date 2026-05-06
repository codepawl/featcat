import { useEffect, useState } from 'react'

/**
 * Returns `value` after it has stayed unchanged for `delay` ms.
 *
 * Used to avoid round-tripping a server query on every keystroke in search
 * inputs. Default delay matches T1.4 spec target (search response < 500ms,
 * so 300ms debounce keeps perceived latency under ~800ms).
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}
