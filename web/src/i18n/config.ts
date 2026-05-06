import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import viCommon from '../locales/vi/common.json'
import viSidebar from '../locales/vi/sidebar.json'
import viDashboard from '../locales/vi/dashboard.json'
import viFeatures from '../locales/vi/features.json'
import viGroups from '../locales/vi/groups.json'
import viSimilarity from '../locales/vi/similarity.json'
import viAudit from '../locales/vi/audit.json'
import viMonitoring from '../locales/vi/monitoring.json'
import viJobs from '../locales/vi/jobs.json'
import viChat from '../locales/vi/chat.json'
import viSettings from '../locales/vi/settings.json'
import viModals from '../locales/vi/modals.json'
import viErrors from '../locales/vi/errors.json'

import enCommon from '../locales/en/common.json'
import enSidebar from '../locales/en/sidebar.json'
import enDashboard from '../locales/en/dashboard.json'
import enFeatures from '../locales/en/features.json'
import enGroups from '../locales/en/groups.json'
import enSimilarity from '../locales/en/similarity.json'
import enAudit from '../locales/en/audit.json'
import enMonitoring from '../locales/en/monitoring.json'
import enJobs from '../locales/en/jobs.json'
import enChat from '../locales/en/chat.json'
import enSettings from '../locales/en/settings.json'
import enModals from '../locales/en/modals.json'
import enErrors from '../locales/en/errors.json'

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
    groups: viGroups,
    similarity: viSimilarity,
    audit: viAudit,
    monitoring: viMonitoring,
    jobs: viJobs,
    chat: viChat,
    settings: viSettings,
    modals: viModals,
    errors: viErrors,
  },
  en: {
    common: enCommon,
    sidebar: enSidebar,
    dashboard: enDashboard,
    features: enFeatures,
    groups: enGroups,
    similarity: enSimilarity,
    audit: enAudit,
    monitoring: enMonitoring,
    jobs: enJobs,
    chat: enChat,
    settings: enSettings,
    modals: enModals,
    errors: enErrors,
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
