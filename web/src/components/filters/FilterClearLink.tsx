/** "Clear all filters" text link. Returns null when `show` is false so
 *  callers don't have to wrap the JSX in their own condition.
 *
 *  Audit reference: Pattern 14 (Filter bar primitives).
 */

import { useTranslation } from 'react-i18next'

export interface FilterClearLinkProps {
  show: boolean
  onClick: () => void
  /** Defaults to t('actions.clear_all_filters', { ns: 'common' }). */
  label?: string
}

export function FilterClearLink({ show, onClick, label }: FilterClearLinkProps) {
  const { t } = useTranslation('common')
  if (!show) return null
  return (
    <button onClick={onClick} className="text-xs text-brand hover:underline">
      {label ?? t('actions.clear_all_filters')}
    </button>
  )
}
