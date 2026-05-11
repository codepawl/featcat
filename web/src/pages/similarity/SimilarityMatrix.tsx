import { useTranslation } from 'react-i18next'

export function SimilarityMatrix() {
  const { t } = useTranslation('similarity')
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center text-sm text-[var(--text-tertiary)]">
      <div className="font-medium text-[var(--text-secondary)] mb-1">
        {t('matrix.placeholder.title')}
      </div>
      <div>{t('matrix.placeholder.subtitle')}</div>
    </div>
  )
}
