import { useState, useEffect } from 'react'
import { Check, Copy, Download } from 'lucide-react'
import { api } from '../api'
import { FeatureSelector } from './FeatureSelector'
import { Modal } from './Modal'

interface ExportModalProps {
  open: boolean
  onClose: () => void
  title: string
  featureSpecs: string[]
  groupName?: string
}

export function ExportModal({ open, onClose, title, featureSpecs, groupName }: ExportModalProps) {
  const [format, setFormat] = useState<'parquet' | 'csv'>('parquet')
  const [joinOn, setJoinOn] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [exporting, setExporting] = useState(false)
  const [result, setResult] = useState<{
    export_id: string; download_url: string; feature_count: number; row_count: number;
    sources_used: string[]; code_snippet: string; warnings: string[]; file_size: number;
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (open) {
      setSelected(new Set(featureSpecs))
      setResult(null)
      setError(null)
      setFormat('parquet')
      setJoinOn('')
      setCopied(false)
    }
  }, [open, featureSpecs])

  const handleExport = async () => {
    setExporting(true)
    setError(null)
    try {
      const specs = [...selected]
      const res = await api.export.create({
        feature_specs: groupName ? undefined : specs,
        group_name: groupName,
        join_on: joinOn || null,
        format,
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    }
    setExporting(false)
  }

  const handleDownload = () => {
    if (!result) return
    window.open(api.export.download(result.export_id), '_blank')
  }

  const handleCopy = () => {
    if (!result) return
    navigator.clipboard.writeText(result.code_snippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const sizeStr = result ? (result.file_size / (1024 * 1024)).toFixed(1) + ' MB' : ''

  return (
    <Modal open={open} onClose={onClose} title={`Export: ${title}`} maxWidth="max-w-lg" actions={
      result ? (
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
          Close
        </button>
      ) : (
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || selected.size === 0}
            className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50"
          >
            {exporting ? 'Exporting...' : `Export & Download (${selected.size})`}
          </button>
        </>
      )
    }>
      {result ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
            <Check size={16} />
            <span className="text-sm font-medium">
              Export complete &mdash; {result.row_count.toLocaleString()} rows,{' '}
              {result.feature_count} features, {sizeStr}
            </span>
          </div>

          <button
            onClick={handleDownload}
            className="flex items-center gap-2 w-full px-4 py-2.5 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-emphasis transition-colors"
          >
            <Download size={16} /> Download {format === 'csv' ? 'CSV' : 'Parquet'}
          </button>

          {result.warnings.length > 0 && (
            <div className="space-y-1">
              {result.warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-500">{w}</p>
              ))}
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
                Python snippet
              </span>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-xs text-accent hover:underline"
              >
                {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
              </button>
            </div>
            <pre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
              {result.code_snippet}
            </pre>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {error && <p className="text-xs text-red-500">{error}</p>}

          <div>
            <label className="block text-xs font-medium mb-2">Format</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" checked={format === 'parquet'} onChange={() => setFormat('parquet')} className="accent-accent" />
                Parquet (recommended)
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" checked={format === 'csv'} onChange={() => setFormat('csv')} className="accent-accent" />
                CSV
              </label>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Join column</label>
            <input
              value={joinOn}
              onChange={e => setJoinOn(e.target.value)}
              placeholder="auto-detect"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none"
            />
            <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
              Leave empty to auto-detect common column across sources
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium mb-2">Features to include:</label>
            <FeatureSelector
              features={featureSpecs.map(spec => ({
                spec,
                source: spec.split('.')[0],
                column: spec.split('.').pop() || spec,
                dtype: '',
                has_doc: false,
              }))}
              selected={selected}
              onChange={setSelected}
              maxHeight="200px"
              showAISuggest={false}
            />
          </div>
        </div>
      )}
    </Modal>
  )
}
