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
      className={`fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity ${closing ? 'opacity-0' : 'opacity-100'}`}
      onClick={handleClose}
    >
      <div
        className={`bg-[var(--bg-primary)] rounded-xl shadow-xl ${maxWidth} w-[90%] max-h-[80vh] flex flex-col ${closing ? 'animate-modal-out' : 'animate-modal-in'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button
            onClick={handleClose}
            className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors p-1 -mr-1"
          >
            <X size={18} />
          </button>
        </div>
        <div className="px-6 pb-5 overflow-y-auto flex-1">{children}</div>
        {actions && <div className="flex gap-2 justify-end px-6 pb-5 pt-2 border-t border-[var(--border-subtle)]">{actions}</div>}
      </div>
    </div>
  )
}
