import 'i18next'
import common from '../locales/en/common.json'
import sidebar from '../locales/en/sidebar.json'
import dashboard from '../locales/en/dashboard.json'
import features from '../locales/en/features.json'
import businessMetrics from '../locales/en/businessMetrics.json'
import featureRegistry from '../locales/en/featureRegistry.json'
import groups from '../locales/en/groups.json'
import sources from '../locales/en/sources.json'
import similarity from '../locales/en/similarity.json'
import lineage from '../locales/en/lineage.json'
import audit from '../locales/en/audit.json'
import monitoring from '../locales/en/monitoring.json'
import jobs from '../locales/en/jobs.json'
import chat from '../locales/en/chat.json'
import settings from '../locales/en/settings.json'
import modals from '../locales/en/modals.json'
import errors from '../locales/en/errors.json'
import actions from '../locales/en/actions.json'
import help from '../locales/en/help.json'
import glossary from '../locales/en/glossary.json'
import search from '../locales/en/search.json'
import datasetBuilds from '../locales/en/datasetBuilds.json'
import materializationRuns from '../locales/en/materializationRuns.json'
import materializationSchedules from '../locales/en/materializationSchedules.json'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common'
    resources: {
      common: typeof common
      sidebar: typeof sidebar
      dashboard: typeof dashboard
      features: typeof features
      businessMetrics: typeof businessMetrics
      featureRegistry: typeof featureRegistry
      groups: typeof groups
      sources: typeof sources
      similarity: typeof similarity
      lineage: typeof lineage
      audit: typeof audit
      monitoring: typeof monitoring
      jobs: typeof jobs
      chat: typeof chat
      settings: typeof settings
      modals: typeof modals
      errors: typeof errors
      actions: typeof actions
      help: typeof help
      glossary: typeof glossary
      search: typeof search
      datasetBuilds: typeof datasetBuilds
      materializationRuns: typeof materializationRuns
      materializationSchedules: typeof materializationSchedules
    }
  }
}
