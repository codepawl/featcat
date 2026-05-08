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
      'text-sm leading-relaxed',
      '[&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0',
      '[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-base [&_h1]:font-semibold',
      '[&_h2]:mt-3 [&_h2]:mb-2 [&_h2]:text-sm [&_h2]:font-semibold',
      '[&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-medium',
      '[&_ul]:my-2 [&_ul]:ml-5 [&_ul]:list-disc',
      '[&_ol]:my-2 [&_ol]:ml-5 [&_ol]:list-decimal',
      '[&_li]:my-0.5',
      '[&_pre]:my-2 [&_pre]:rounded-md [&_pre]:bg-muted/50 [&_pre]:p-3 [&_pre]:overflow-x-auto',
      '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs',
      '[&_pre_code]:bg-transparent [&_pre_code]:p-0',
      '[&_a]:text-brand [&_a]:underline-offset-2 hover:[&_a]:underline',
      '[&_strong]:font-semibold',
      '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-muted-foreground',
      className,
    )}
  >
    <Streamdown components={components} plugins={plugins}>
      {children}
    </Streamdown>
  </div>
))

Response.displayName = 'Response'
