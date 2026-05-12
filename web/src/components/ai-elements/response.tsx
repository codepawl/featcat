import type { HTMLAttributes, ReactNode } from 'react'
import { memo } from 'react'
import { Streamdown, useIsCodeFenceIncomplete } from 'streamdown'
import type { BundledLanguage } from 'streamdown'
import { cjk } from '@streamdown/cjk'
import { math } from '@streamdown/math'

import { CodeBlock, CodeBlockCopyButton } from '@/components/ai-elements/code-block'
import { code } from '@/components/ai-elements/shiki-slim'
import { cn } from '@/lib/utils'

const plugins = { cjk, code, math }

// Streamdown's `components.code` override receives both inline (`backtick`) and
// fenced (```...```) code. We distinguish via className: fenced blocks come
// through with `language-<id>`, while inline code has no className. Inline
// code keeps default rendering; fenced code is replaced with our AI Elements
// <CodeBlock> + copy button so chat replies match the SQL CodeBlocks rendered
// in ResultTable.
type CodeElProps = HTMLAttributes<HTMLElement> & { children?: ReactNode }

const FencedCodeBlock = ({
  language,
  source,
}: {
  language: string
  source: string
}) => {
  // Streamdown sets a context flag while the fence is unclosed. Gate the
  // copy button until the block is complete (avoids copying mid-stream).
  const isIncomplete = useIsCodeFenceIncomplete()
  return (
    <CodeBlock
      className="relative my-2"
      code={source}
      language={(language || 'plaintext') as BundledLanguage}
    >
      {!isIncomplete && <CodeBlockCopyButton className="absolute right-2 top-2" />}
    </CodeBlock>
  )
}

const codeRenderer = ({ className, children, ...rest }: CodeElProps) => {
  // Fenced blocks always come with a `language-X` className from remark.
  // Anything else is inline — preserve the default <code> rendering.
  const match = /^language-([\w-]+)/.exec(className ?? '')
  if (!match) {
    return (
      <code className={className} {...rest}>
        {children}
      </code>
    )
  }
  const language = match[1]
  // children is the raw source text. Strip the trailing newline added by
  // remark (matches how AI Elements CodeBlock expects clean code).
  const source = String(children ?? '').replace(/\n$/, '')
  return <FencedCodeBlock language={language} source={source} />
}

const components = {
  code: codeRenderer,
}

export type ResponseProps = {
  children: string
  className?: string
}

export const Response = memo(({ children, className }: ResponseProps) => (
  <div
    className={cn(
      // Tighter prose styling tuned to match the visual rhythm of
      // ChatGPT/Claude: subtler inline code (no chip-like bg), generous
      // line-height, paragraph bottom-only spacing, ordered/unordered lists
      // with plain markers (no background tint).
      'text-[14px] leading-relaxed',
      // Paragraph: bottom-only spacing keeps consecutive paragraphs from
      // double-stacking, and the first/last neighbour rules avoid edge
      // wobble inside a chat bubble.
      '[&_p]:mb-3 [&_p]:mt-0 [&_p:last-child]:mb-0',
      // Headings stay tight; sizes step down so they don't dominate a
      // chat response (large h1s look like a marketing page).
      '[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-base [&_h1]:font-semibold',
      '[&_h2]:mt-3 [&_h2]:mb-2 [&_h2]:text-[15px] [&_h2]:font-semibold',
      '[&_h3]:mt-3 [&_h3]:mb-1.5 [&_h3]:text-sm [&_h3]:font-semibold',
      // Lists: standard outside markers with comfortable spacing.
      '[&_ul]:my-2 [&_ul]:pl-5 [&_ul]:list-disc [&_ul]:space-y-1',
      '[&_ol]:my-2 [&_ol]:pl-5 [&_ol]:list-decimal [&_ol]:space-y-1',
      '[&_li]:pl-1 [&_li]:marker:text-[var(--text-tertiary)]',
      // Fenced code: muted box, no border, horizontal scroll when long.
      '[&_pre]:my-3 [&_pre]:rounded-lg [&_pre]:bg-[var(--bg-tertiary)] [&_pre]:p-3 [&_pre]:overflow-x-auto',
      // Inline code: subtle — uses the tertiary bg (not the brighter
      // shadcn muted token) so it reads as text-with-tint rather than
      // a chip/badge. Compact padding matches the surrounding line height.
      '[&_code]:font-mono [&_code]:text-[13px] [&_code]:bg-[var(--bg-tertiary)] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded',
      // Code inside a fenced block strips its own bg/padding so the
      // outer `<pre>` provides the chrome.
      '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:rounded-none',
      // Links keep brand color; underlining moved to hover so dense
      // tables of links don't look noisy.
      '[&_a]:text-brand [&_a]:underline-offset-2 hover:[&_a]:underline',
      '[&_strong]:font-semibold',
      '[&_blockquote]:border-l-2 [&_blockquote]:border-[var(--border-default)] [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-[var(--text-secondary)] [&_blockquote]:my-3',
      // Tables (GFM): scrollable in narrow viewports, subtle row dividers.
      '[&_table]:my-3 [&_table]:w-full [&_table]:text-[13px] [&_table]:border-collapse',
      '[&_th]:text-left [&_th]:py-1.5 [&_th]:px-2 [&_th]:border-b [&_th]:border-[var(--border-default)] [&_th]:font-medium [&_th]:text-[var(--text-tertiary)]',
      '[&_td]:py-1.5 [&_td]:px-2 [&_td]:border-b [&_td]:border-[var(--border-subtle)]',
      className,
    )}
  >
    <Streamdown components={components} plugins={plugins}>
      {children}
    </Streamdown>
  </div>
))

Response.displayName = 'Response'
