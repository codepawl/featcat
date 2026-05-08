/**
 * Slim Shiki code-highlighter plugin for Streamdown.
 *
 * Replaces `@streamdown/code` (which pulls in shiki's full bundle of ~200
 * languages — each registered via dynamic import, producing ~600 small
 * async chunks at build time).
 *
 * This plugin uses shiki's slim core (`shiki/core` + `shiki/engine/javascript`)
 * and statically lists ~10 commonly used languages. Vite/Rollup only chunks
 * the explicit `import('shiki/langs/<name>.mjs')` calls below — nothing else.
 *
 * Editing the whitelist:
 *  - Add a new entry to `LANG_LOADERS` keyed by the canonical id.
 *  - Add aliases (e.g. `shell` -> `bash`) to `LANG_ALIASES`.
 *  - Languages NOT in the whitelist render as plaintext (no syntax highlight,
 *    no crash). The chat will still display the code block correctly.
 */
import type { CodeHighlighterPlugin, ThemeInput } from 'streamdown'
import type {
  HighlighterCore,
  HighlighterGeneric,
  LanguageRegistration,
  MaybeArray,
  ThemeRegistrationAny,
} from '@shikijs/types'
import { createHighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'

// Streamdown does not export its HighlightResult/HighlightToken types,
// so we mirror them locally. They are structurally compatible with
// shiki's TokensResult.
interface HighlightToken {
  bgColor?: string
  color?: string
  content: string
  htmlAttrs?: Record<string, string>
  htmlStyle?: Record<string, string>
  offset?: number
}
interface HighlightResult {
  bg?: string
  fg?: string
  rootStyle?: string | false
  tokens: HighlightToken[][]
}

// Whitelist: each entry is a canonical shiki language id mapped to a
// lazy loader. ONLY these `import('shiki/langs/<id>.mjs')` calls are
// followed by Vite — adding/removing here is the source of truth.
type LangModule = MaybeArray<LanguageRegistration>
const LANG_LOADERS: Record<string, () => Promise<LangModule>> = {
  sql: () => import('shiki/langs/sql.mjs').then((m) => m.default as LangModule),
  python: () => import('shiki/langs/python.mjs').then((m) => m.default as LangModule),
  json: () => import('shiki/langs/json.mjs').then((m) => m.default as LangModule),
  bash: () => import('shiki/langs/bash.mjs').then((m) => m.default as LangModule),
  typescript: () =>
    import('shiki/langs/typescript.mjs').then((m) => m.default as LangModule),
  javascript: () =>
    import('shiki/langs/javascript.mjs').then((m) => m.default as LangModule),
  tsx: () => import('shiki/langs/tsx.mjs').then((m) => m.default as LangModule),
  jsx: () => import('shiki/langs/jsx.mjs').then((m) => m.default as LangModule),
  yaml: () => import('shiki/langs/yaml.mjs').then((m) => m.default as LangModule),
  markdown: () =>
    import('shiki/langs/markdown.mjs').then((m) => m.default as LangModule),
}

// Aliases: alternative ids that should resolve to a canonical loader above.
const LANG_ALIASES: Record<string, string> = {
  shell: 'bash',
  sh: 'bash',
  zsh: 'bash',
  py: 'python',
  ts: 'typescript',
  js: 'javascript',
  yml: 'yaml',
  md: 'markdown',
}

const PLAINTEXT_IDS = new Set(['plaintext', 'text', 'txt', 'plain'])

const SUPPORTED_LANGS: ReadonlySet<string> = new Set([
  ...Object.keys(LANG_LOADERS),
  ...Object.keys(LANG_ALIASES),
  ...PLAINTEXT_IDS,
])

const THEME_LOADERS: Record<string, () => Promise<ThemeRegistrationAny>> = {
  'github-light': () =>
    import('shiki/themes/github-light.mjs').then(
      (m) => m.default as ThemeRegistrationAny,
    ),
  'github-dark': () =>
    import('shiki/themes/github-dark.mjs').then(
      (m) => m.default as ThemeRegistrationAny,
    ),
}

const DEFAULT_THEMES: [ThemeInput, ThemeInput] = ['github-light', 'github-dark']

const normalizeLang = (raw: string): string => {
  const lower = raw.trim().toLowerCase()
  if (LANG_LOADERS[lower]) return lower
  if (LANG_ALIASES[lower]) return LANG_ALIASES[lower]
  if (PLAINTEXT_IDS.has(lower)) return 'plaintext'
  return 'plaintext'
}

const themeName = (theme: ThemeInput): string =>
  typeof theme === 'string' ? theme : (theme.name ?? 'custom')

interface CodePluginOptions {
  themes?: [ThemeInput, ThemeInput]
}

// Resolve a theme input (string id or registration object) to a registration
// the slim core can consume. String ids that aren't in our loader map are
// passed through as-is — shiki may still reject them, which we surface via
// the error path in highlight().
const resolveThemeInput = async (t: ThemeInput): Promise<ThemeRegistrationAny> => {
  if (typeof t !== 'string') return t
  const loader = THEME_LOADERS[t]
  if (loader) return loader()
  // Fallback: cast string to registration; shiki throws if invalid.
  return t as unknown as ThemeRegistrationAny
}

export function createCodePlugin(
  options: CodePluginOptions = {},
): CodeHighlighterPlugin {
  const themes = options.themes ?? DEFAULT_THEMES

  // Single highlighter instance, lazily initialized + augmented with extra
  // langs as they are encountered.
  let highlighterPromise: Promise<HighlighterCore> | null = null
  const loadedLangs = new Set<string>()

  const ensureHighlighter = async (): Promise<HighlighterCore> => {
    if (!highlighterPromise) {
      highlighterPromise = (async () => {
        const themeMods = await Promise.all(themes.map(resolveThemeInput))
        return createHighlighterCore({
          themes: themeMods,
          langs: [],
          engine: createJavaScriptRegexEngine({ forgiving: true }),
        })
      })()
    }
    return highlighterPromise
  }

  const ensureLang = async (
    highlighter: HighlighterCore,
    lang: string,
  ): Promise<string> => {
    if (lang === 'plaintext') return 'text'
    if (loadedLangs.has(lang)) return lang
    const loader = LANG_LOADERS[lang]
    if (!loader) return 'text'
    const mod = await loader()
    await highlighter.loadLanguage(mod)
    loadedLangs.add(lang)
    return lang
  }

  // Result cache: key = (lang, themeNames, code-fingerprint).
  const resultCache = new Map<string, HighlightResult>()
  // Pending callbacks for in-flight highlight requests.
  const subscribers = new Map<string, Set<(result: HighlightResult) => void>>()

  const cacheKey = (
    code: string,
    lang: string,
    themePair: [string, string],
  ): string => {
    const head = code.slice(0, 100)
    const tail = code.length > 100 ? code.slice(-100) : ''
    return `${lang}:${themePair[0]}:${themePair[1]}:${code.length}:${head}:${tail}`
  }

  const plugin: CodeHighlighterPlugin = {
    name: 'shiki',
    type: 'code-highlighter',
    supportsLanguage(language) {
      return SUPPORTED_LANGS.has(String(language).trim().toLowerCase())
    },
    // The plugin contract types this as `BundledLanguage[]`. We return our
    // whitelist (a subset of valid ids) cast to the same type.
    getSupportedLanguages() {
      return Array.from(SUPPORTED_LANGS) as ReturnType<
        CodeHighlighterPlugin['getSupportedLanguages']
      >
    },
    getThemes() {
      return themes
    },
    highlight({ code, language, themes: requestedThemes }, callback) {
      const lang = normalizeLang(String(language))
      const themePair: [string, string] = [
        themeName(requestedThemes[0]),
        themeName(requestedThemes[1]),
      ]
      const key = cacheKey(code, lang, themePair)

      const cached = resultCache.get(key)
      if (cached) return cached

      if (callback) {
        if (!subscribers.has(key)) subscribers.set(key, new Set())
        subscribers.get(key)?.add(callback)
      }

      void (async () => {
        try {
          const highlighter = await ensureHighlighter()
          const resolvedLang = await ensureLang(highlighter, lang)
          const result = highlighter.codeToTokens(code, {
            lang: resolvedLang,
            themes: { light: themePair[0], dark: themePair[1] },
          }) as HighlightResult
          resultCache.set(key, result)
          const subs = subscribers.get(key)
          if (subs) {
            for (const sub of subs) sub(result)
            subscribers.delete(key)
          }
        } catch (err) {
          // Silently fall through — Streamdown shows the code block as plain
          // text when no tokens are produced.
          console.error('[shiki-slim] highlight failed:', err)
          subscribers.delete(key)
        }
      })()

      return null
    },
  }
  return plugin
}

export const code: CodeHighlighterPlugin = createCodePlugin()

/**
 * Drop-in replacement for shiki's `createHighlighter({ langs, themes })`,
 * scoped to the same whitelist as the Streamdown plugin above. Used by
 * `code-block.tsx` so the AI Elements <CodeBlock> doesn't pull in the full
 * shiki bundle either.
 *
 * Languages outside the whitelist are silently substituted with 'text'
 * (plaintext) — matches the original code-block.tsx fallback behavior.
 *
 * Return is `HighlighterGeneric<string, string>`: structurally compatible
 * with whatever `HighlighterGeneric<L, T>` the caller declares, since the
 * generic parameters only constrain `loadLanguage`/`loadTheme` argument
 * types. The runtime is plain `HighlighterCore`.
 */
type ShikiCompatibleHighlighter = HighlighterGeneric<string, string>
export async function createSlimHighlighter(opts: {
  langs: ReadonlyArray<string>
  themes: ReadonlyArray<string | ThemeInput>
}): Promise<ShikiCompatibleHighlighter> {
  const themeMods = await Promise.all(
    opts.themes.map((t) => resolveThemeInput(t as ThemeInput)),
  )
  const langModsRaw = await Promise.all(
    opts.langs.map(async (raw) => {
      const lang = normalizeLang(String(raw))
      if (lang === 'plaintext') return null
      const loader = LANG_LOADERS[lang]
      if (!loader) return null
      return loader()
    }),
  )
  const validLangs = langModsRaw.filter((m): m is LangModule => m !== null)
  const highlighter = await createHighlighterCore({
    themes: themeMods,
    langs: validLangs,
    engine: createJavaScriptRegexEngine({ forgiving: true }),
  })
  // Widen the generic key parameters — the runtime is identical, the
  // generics only constrain `loadLanguage`/`loadTheme` argument types.
  return highlighter as unknown as ShikiCompatibleHighlighter
}
