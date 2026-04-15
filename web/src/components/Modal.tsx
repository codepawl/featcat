import { useEffect, useState, useCallback } from 'react'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  actions?: React.ReactNode
  maxWidth?: string
}

export function Modal({ open, onClose, title, children, actions, maxWidth = 'max-w-lg' }: Props) {
  const [closing, setClosing] = useState(false)

  const handleClose = useCallback(() => {
    setClosing(true)
    setTimeout(onClose, 150)
  }, [onClose])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    if (open) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, handleClose])

  useEffect(() => {
    if (open) setClosing(false)
  }, [open])

  if (!open) return null

  return (
    <div
      className={`fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity ${closing ? 'opacity-0' : 'opacity-100'}`}
      onClick={handleClose}
    >
      <div
        className={`bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-2xl shadow-2xl ${maxWidth} w-[calc(100%-2rem)] sm:w-[90%] max-h-[85vh] sm:max-h-[80vh] flex flex-col ${closing ? 'animate-modal-out' : 'animate-modal-in'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 sm:px-6 pt-5 pb-3 border-b border-[var(--border-subtle)]">
          <h2 className="text-base font-semibold">{title}</h2>
          <button
            onClick={handleClose}
            className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors p-1 -mr-1 rounded-lg hover:bg-[var(--bg-tertiary)]"
          >
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>
        <div className="px-5 sm:px-6 py-4 overflow-y-auto overscroll-contain flex-1">{children}</div>
        {actions && (
          <div className="flex gap-2 justify-end px-5 sm:px-6 pb-4 pt-3 border-t border-[var(--border-subtle)]">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
