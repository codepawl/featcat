import { NavLink } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { ThemeToggle } from './ThemeToggle';

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/features', label: 'Features' },
  { to: '/monitoring', label: 'Monitoring' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/chat', label: 'AI Chat' },
];

export function Sidebar() {
  const [llm, setLlm] = useState<{ ok: boolean; model: string }>({ ok: false, model: 'checking...' });
  const [serverOk, setServerOk] = useState(false);

  useEffect(() => {
    api.health()
      .then((d) => {
        setServerOk(true);
        setLlm({ ok: !!d.llm, model: d.model || (d.llm ? 'connected' : 'offline') });
      })
      .catch(() => setServerOk(false));
  }, []);

  return (
    <nav className="w-[220px] shrink-0 sticky top-0 h-screen overflow-y-auto flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] py-4 transition-all">
      <div className="font-mono text-base font-bold text-accent px-5 pb-5 tracking-tight">featcat</div>
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === '/'}
          className={({ isActive }) =>
            `block px-5 py-2 text-[13px] border-l-2 transition-all no-underline ${
              isActive
                ? 'text-accent border-accent bg-accent-subtle'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] hover:pl-6'
            }`
          }
        >
          {n.label}
        </NavLink>
      ))}
      <div className="mt-auto px-5 text-xs text-[var(--text-tertiary)] flex flex-col gap-1.5">
        <div><span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${serverOk ? 'bg-green-500' : 'bg-[var(--border-default)]'}`} /> Server</div>
        <div><span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${llm.ok ? 'bg-green-500' : 'bg-red-500'}`} /> LLM: {llm.model}</div>
        <ThemeToggle />
      </div>
    </nav>
  );
}
