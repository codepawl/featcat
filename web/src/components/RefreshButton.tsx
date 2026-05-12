/** Standardized refresh button: secondary-style border + spinning icon while
 *  loading + auto-disabled while loading. Replaces the same icon-button JSX
 *  copied across 8+ pages.
 *
 *  Audit reference: Pattern 17 (Refresh button).
 */

import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface RefreshButtonProps {
  onClick: () => void
  loading: boolean
  /** Override the default `t('actions.refresh', { ns: 'common' })` label. */
  label?: string
  /** `default` = px-3 py-1.5; `compact` = px-2 py-1 (matches dense toolbars). */
  size?: 'default' | 'compact'
}

const PADDING: Record<string, string> = {
  default: 'px-3 py-1.5',
  compact: 'px-2 py-1',
}

export function RefreshButton({ onClick, loading, label, size = 'default' }: RefreshButtonProps) {
  const { t } = useTranslation('common')
  const text = label ?? t('actions.refresh')
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`flex items-center gap-1.5 ${PADDING[size]} text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50 transition-colors`}
    >
      <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
      {text}
    </button>
  )
}
