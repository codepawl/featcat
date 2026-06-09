export function formatLines(values: string[] | undefined | null): string {
  return (values ?? []).join('\n')
}

export function parseLines(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export function formatPrettyJson(value: unknown): string {
  if (value == null) return ''
  return JSON.stringify(value, null, 2)
}

export function parseJsonObject<T extends Record<string, unknown>>(raw: string): T {
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Expected a JSON object')
  }
  return parsed as T
}

export function parseJsonValue<T>(raw: string): T {
  return JSON.parse(raw) as T
}
