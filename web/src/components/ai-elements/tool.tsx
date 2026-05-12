"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { DynamicToolUIPart, ToolUIPart } from "ai";
import { ChevronDownIcon, WrenchIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { isValidElement } from "react";

import { CodeBlock } from "./code-block";

/** Minimal tool-call display.
 *
 *  Collapsed (default): single-line `[🔧] [name]  [● status]  [chevron]` —
 *  visually quieter than the response text so reads as supporting context.
 *  Expanded: input/output blocks tucked under, no "RESULT" / "Parameters"
 *  section headers (the chrome from the previous version was busy).
 *
 *  Multiple tool calls in one message stack vertically with `space-y-0.5`
 *  on the caller (Chat.tsx already groups them with `mb-3 space-y-2`).
 */

export type ToolProps = ComponentProps<typeof Collapsible>;

export const Tool = ({ className, ...props }: ToolProps) => (
  <Collapsible
    className={cn("group not-prose w-full", className)}
    {...props}
  />
);

export type ToolPart = ToolUIPart | DynamicToolUIPart;

export type ToolHeaderProps = {
  title?: string;
  className?: string;
} & (
  | { type: ToolUIPart["type"]; state: ToolUIPart["state"]; toolName?: never }
  | {
      type: DynamicToolUIPart["type"];
      state: DynamicToolUIPart["state"];
      toolName: string;
    }
);

const STATUS_DOT: Record<ToolPart["state"], string> = {
  "approval-requested": "bg-[var(--warning)]",
  "approval-responded": "bg-[var(--brand)]",
  "input-available": "bg-[var(--brand)] animate-pulse",
  "input-streaming": "bg-[var(--text-tertiary)]",
  "output-available": "bg-[var(--success)]",
  "output-denied": "bg-[var(--warning)]",
  "output-error": "bg-[var(--danger)]",
};

const STATUS_LABEL: Record<ToolPart["state"], string> = {
  "approval-requested": "Awaiting approval",
  "approval-responded": "Responded",
  "input-available": "Running",
  "input-streaming": "Pending",
  "output-available": "Completed",
  "output-denied": "Denied",
  "output-error": "Error",
};

export const ToolHeader = ({
  className,
  title,
  type,
  state,
  toolName,
  ...props
}: ToolHeaderProps) => {
  const derivedName =
    type === "dynamic-tool" ? toolName : type.split("-").slice(1).join("-");

  return (
    <CollapsibleTrigger
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] transition-colors",
        className
      )}
      {...props}
    >
      <WrenchIcon className="size-3.5 text-[var(--text-tertiary)] shrink-0" />
      <span className="font-mono text-[12.5px] text-[var(--text-primary)]">
        {title ?? derivedName}
      </span>
      <span
        title={STATUS_LABEL[state]}
        aria-label={STATUS_LABEL[state]}
        className={cn("inline-block size-1.5 rounded-full shrink-0", STATUS_DOT[state])}
      />
      <span className="text-[11px] text-[var(--text-tertiary)] hidden sm:inline">
        {STATUS_LABEL[state]}
      </span>
      <ChevronDownIcon className="size-3.5 text-[var(--text-tertiary)] ml-auto transition-transform group-data-[state=open]:rotate-180" />
    </CollapsibleTrigger>
  );
};

export type ToolContentProps = ComponentProps<typeof CollapsibleContent>;

export const ToolContent = ({ className, ...props }: ToolContentProps) => (
  <CollapsibleContent
    className={cn(
      "data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 space-y-2 px-2 pb-2 pt-1 outline-none data-[state=closed]:animate-out data-[state=open]:animate-in",
      className
    )}
    {...props}
  />
);

export type ToolInputProps = ComponentProps<"div"> & {
  input: ToolPart["input"];
};

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => {
  // Only render input when it carries content beyond an empty object.
  const hasContent =
    input !== undefined && input !== null && (typeof input !== "object" || Object.keys(input as object).length > 0);
  if (!hasContent) return null;
  return (
    <div className={cn("overflow-hidden", className)} {...props}>
      <div className="rounded-md bg-[var(--bg-tertiary)] text-[12px]">
        <CodeBlock code={JSON.stringify(input, null, 2)} language="json" />
      </div>
    </div>
  );
};

export type ToolOutputProps = ComponentProps<"div"> & {
  output: ToolPart["output"];
  errorText: ToolPart["errorText"];
};

export const ToolOutput = ({
  className,
  output,
  errorText,
  ...props
}: ToolOutputProps) => {
  if (!(output || errorText)) {
    return null;
  }

  // Short string output renders as plain text (no syntax-highlighted block).
  if (typeof output === "string" && output.length < 200 && !output.includes("\n")) {
    return (
      <div
        className={cn(
          "rounded-md px-3 py-2 font-mono text-[12px]",
          errorText
            ? "bg-[var(--danger-subtle-bg)] text-[var(--danger)]"
            : "bg-[var(--bg-tertiary)] text-[var(--text-primary)]",
          className,
        )}
        {...props}
      >
        {errorText ?? output}
      </div>
    );
  }

  let Output = <div>{output as ReactNode}</div>;

  if (typeof output === "object" && !isValidElement(output)) {
    Output = (
      <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />
    );
  } else if (typeof output === "string") {
    Output = <CodeBlock code={output} language="json" />;
  }

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-md text-[12px]",
        errorText
          ? "bg-[var(--danger-subtle-bg)] text-[var(--danger)] px-3 py-2"
          : "bg-[var(--bg-tertiary)] text-[var(--text-primary)]",
        className,
      )}
      {...props}
    >
      {errorText && <div>{errorText}</div>}
      {Output}
    </div>
  );
};
