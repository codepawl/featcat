import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import viCommon from '../locales/vi/common.json'
import viSidebar from '../locales/vi/sidebar.json'
import viDashboard from '../locales/vi/dashboard.json'
import viFeatures from '../locales/vi/features.json'
import viBusinessMetrics from '../locales/vi/businessMetrics.json'
import viFeatureRegistry from '../locales/vi/featureRegistry.json'
import viGroups from '../locales/vi/groups.json'
import viSources from '../locales/vi/sources.json'
import viSimilarity from '../locales/vi/similarity.json'
import viLineage from '../locales/vi/lineage.json'
import viAudit from '../locales/vi/audit.json'
import viMonitoring from '../locales/vi/monitoring.json'
import viJobs from '../locales/vi/jobs.json'
import viChat from '../locales/vi/chat.json'
import viSettings from '../locales/vi/settings.json'
import viModals from '../locales/vi/modals.json'
import viErrors from '../locales/vi/errors.json'
import viActions from '../locales/vi/actions.json'
import viHelp from '../locales/vi/help.json'
import viGlossary from '../locales/vi/glossary.json'
import viSearch from '../locales/vi/search.json'
import viDatasetBuilds from '../locales/vi/datasetBuilds.json'
import viMaterializationRuns from '../locales/vi/materializationRuns.json'
import viMaterializationSchedules from '../locales/vi/materializationSchedules.json'

import enCommon from '../locales/en/common.json'
import enSidebar from '../locales/en/sidebar.json'
import enDashboard from '../locales/en/dashboard.json'
import enFeatures from '../locales/en/features.json'
import enBusinessMetrics from '../locales/en/businessMetrics.json'
import enFeatureRegistry from '../locales/en/featureRegistry.json'
import enGroups from '../locales/en/groups.json'
import enSources from '../locales/en/sources.json'
import enSimilarity from '../locales/en/similarity.json'
import enLineage from '../locales/en/lineage.json'
import enAudit from '../locales/en/audit.json'
import enMonitoring from '../locales/en/monitoring.json'
import enJobs from '../locales/en/jobs.json'
import enChat from '../locales/en/chat.json'
import enSettings from '../locales/en/settings.json'
import enModals from '../locales/en/modals.json'
import enErrors from '../locales/en/errors.json'
import enActions from '../locales/en/actions.json'
import enHelp from '../locales/en/help.json'
import enGlossary from '../locales/en/glossary.json'
import enSearch from '../locales/en/search.json'
import enDatasetBuilds from '../locales/en/datasetBuilds.json'
import enMaterializationRuns from '../locales/en/materializationRuns.json'
import enMaterializationSchedules from '../locales/en/materializationSchedules.json'

export const SUPPORTED_LANGS = ['vi', 'en'] as const
export type SupportedLang = typeof SUPPORTED_LANGS[number]

export const LANG_LABELS: Record<SupportedLang, string> = {
  vi: 'Tiếng Việt',
  en: 'English',
}

const resources = {
  vi: {
    common: viCommon,
    sidebar: viSidebar,
    dashboard: viDashboard,
    features: viFeatures,
    businessMetrics: viBusinessMetrics,
    featureRegistry: viFeatureRegistry,
    groups: viGroups,
    sources: viSources,
    similarity: viSimilarity,
    lineage: viLineage,
    audit: viAudit,
    monitoring: viMonitoring,
    jobs: viJobs,
    chat: viChat,
    settings: viSettings,
    modals: viModals,
    errors: viErrors,
    actions: viActions,
    help: viHelp,
    glossary: viGlossary,
    search: viSearch,
    datasetBuilds: viDatasetBuilds,
    materializationRuns: viMaterializationRuns,
    materializationSchedules: viMaterializationSchedules,
  },
  en: {
    common: enCommon,
    sidebar: enSidebar,
    dashboard: enDashboard,
    features: enFeatures,
    businessMetrics: enBusinessMetrics,
    featureRegistry: enFeatureRegistry,
    groups: enGroups,
    sources: enSources,
    similarity: enSimilarity,
    lineage: enLineage,
    audit: enAudit,
    monitoring: enMonitoring,
    jobs: enJobs,
    chat: enChat,
    settings: enSettings,
    modals: enModals,
    errors: enErrors,
    actions: enActions,
    help: enHelp,
    glossary: enGlossary,
    search: enSearch,
    datasetBuilds: enDatasetBuilds,
    materializationRuns: enMaterializationRuns,
    materializationSchedules: enMaterializationSchedules,
  },
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGS,
    defaultNS: 'common',
    ns: Object.keys(resources.vi),
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'featcat-lang',
      caches: ['localStorage'],
    },
  })

if (!localStorage.getItem('featcat-lang')) {
  i18n.changeLanguage('vi')
}

export default i18n
