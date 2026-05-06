import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation(['modals', 'common'])
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
      setError(e instanceof Error ? e.message : t('modals:export.errors.export_failed'))
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
    <Modal open={open} onClose={onClose} title={t('modals:export.title', { name: title })} maxWidth="max-w-lg" actions={
      result ? (
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
          {t('common:actions.close')}
        </button>
      ) : (
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
            {t('common:actions.cancel')}
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || selected.size === 0}
            className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50"
          >
            {exporting ? t('modals:export.actions.exporting') : t('modals:export.actions.export_and_download', { count: selected.size })}
          </button>
        </>
      )
    }>
      {result ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-[var(--success)]">
            <Check size={16} />
            <span className="text-sm font-medium">
              {t('modals:export.result.complete_summary', {
                rows: result.row_count.toLocaleString(),
                features: result.feature_count,
                size: sizeStr,
              })}
            </span>
          </div>

          <button
            onClick={handleDownload}
            className="flex items-center gap-2 w-full px-4 py-2.5 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-emphasis transition-colors"
          >
            <Download size={16} /> {format === 'csv' ? t('modals:export.actions.download_csv') : t('modals:export.actions.download_parquet')}
          </button>

          {result.warnings.length > 0 && (
            <div className="space-y-1">
              {result.warnings.map((w, i) => (
                <p key={i} className="text-xs text-[var(--warning)]">{w}</p>
              ))}
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
                {t('modals:export.python_snippet')}
              </span>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-xs text-accent hover:underline"
              >
                {copied ? <><Check size={12} /> {t('common:actions.copied')}</> : <><Copy size={12} /> {t('common:actions.copy')}</>}
              </button>
            </div>
            <pre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
              {result.code_snippet}
            </pre>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {error && <p className="text-xs text-[var(--danger)]">{error}</p>}

          <div>
            <label className="block text-xs font-medium mb-2">{t('modals:export.form.format_label')}</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" checked={format === 'parquet'} onChange={() => setFormat('parquet')} className="accent-accent" />
                {t('modals:export.form.parquet_recommended')}
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" checked={format === 'csv'} onChange={() => setFormat('csv')} className="accent-accent" />
                CSV
              </label>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">{t('modals:export.form.join_column_label')}</label>
            <input
              value={joinOn}
              onChange={e => setJoinOn(e.target.value)}
              placeholder={t('modals:export.form.auto_detect_placeholder')}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none"
            />
            <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
              {t('modals:export.form.auto_detect_help')}
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium mb-2">{t('modals:export.form.features_to_include')}</label>
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
