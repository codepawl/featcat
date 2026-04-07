import { useEffect } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function Modal({ open, onClose, title, children, actions }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 transition-opacity" onClick={onClose}>
      <div className="bg-[var(--bg-primary)] rounded-xl p-6 max-w-lg w-[90%] shadow-xl animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-base font-semibold mb-4">{title}</h2>
        {children}
        {actions && <div className="flex gap-2 justify-end mt-5">{actions}</div>}
      </div>
    </div>
  );
}
