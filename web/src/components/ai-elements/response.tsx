import { memo } from 'react'
import { Streamdown } from 'streamdown'
import { cjk } from '@streamdown/cjk'
import { code } from '@streamdown/code'
import { math } from '@streamdown/math'

import { cn } from '@/lib/utils'

const plugins = { cjk, code, math }

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
    <Streamdown plugins={plugins}>{children}</Streamdown>
  </div>
))

Response.displayName = 'Response'
