import 'i18next'
import common from '../locales/en/common.json'
import sidebar from '../locales/en/sidebar.json'
import dashboard from '../locales/en/dashboard.json'
import features from '../locales/en/features.json'
import groups from '../locales/en/groups.json'
import similarity from '../locales/en/similarity.json'
import audit from '../locales/en/audit.json'
import monitoring from '../locales/en/monitoring.json'
import jobs from '../locales/en/jobs.json'
import chat from '../locales/en/chat.json'
import settings from '../locales/en/settings.json'
import modals from '../locales/en/modals.json'
import errors from '../locales/en/errors.json'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common'
    resources: {
      common: typeof common
      sidebar: typeof sidebar
      dashboard: typeof dashboard
      features: typeof features
      groups: typeof groups
      similarity: typeof similarity
      audit: typeof audit
      monitoring: typeof monitoring
      jobs: typeof jobs
      chat: typeof chat
      settings: typeof settings
      modals: typeof modals
      errors: typeof errors
    }
  }
}
