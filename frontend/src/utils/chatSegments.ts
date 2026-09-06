export const TEXTING_REVEAL_DELAY = {
  baseMs: 350,
  perCharMs: 18,
  minMs: 300,
  maxMs: 1800,
  totalCapMs: 5000,
} as const

type SplitAssistantBubblesOptions = {
  stripActionNarration?: boolean
  /** Stage keeps action narration, but still reveals each paragraph in turn. */
  splitActionNarration?: boolean
}

export function stripActionNarration(content: string): string {
  return (content ?? '')
    .replace(/\*[^*\n]+\*/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

export function splitAssistantBubbles(
  content: string,
  options: SplitAssistantBubblesOptions = {},
): string[] {
  const raw = options.stripActionNarration
    ? stripActionNarration(content)
    : (content ?? '')
  const trimmed = raw.trim()
  if (!trimmed) return []
  if (!options.stripActionNarration
    && !options.splitActionNarration
    && trimmed.includes('*')) return [raw]

  const segments = trimmed
    .split(/\n\s*\n+/)
    .map(part => part.trim())
    .filter(Boolean)

  return segments.length > 0 ? segments : [trimmed]
}

export function revealDelayMs(segment: string): number {
  const length = [...(segment ?? '')].length
  const value = TEXTING_REVEAL_DELAY.baseMs + length * TEXTING_REVEAL_DELAY.perCharMs
  return Math.max(
    TEXTING_REVEAL_DELAY.minMs,
    Math.min(TEXTING_REVEAL_DELAY.maxMs, value),
  )
}

export interface RevealDelayOptions {
  baseMs?: number
  perCharMs?: number
  minMs?: number
  maxMs?: number
  totalCapMs?: number
}

export function revealDelaysFor(
  segments: string[],
  options: RevealDelayOptions = {},
): number[] {
  if (segments.length <= 1) return []

  const baseMs = options.baseMs ?? TEXTING_REVEAL_DELAY.baseMs
  const perCharMs = options.perCharMs ?? TEXTING_REVEAL_DELAY.perCharMs
  const minMs = options.minMs ?? TEXTING_REVEAL_DELAY.minMs
  const maxMs = options.maxMs ?? TEXTING_REVEAL_DELAY.maxMs
  const totalCapMs = options.totalCapMs ?? TEXTING_REVEAL_DELAY.totalCapMs
  const delays = segments.slice(0, -1).map(segment => Math.max(
    minMs,
    Math.min(maxMs, baseMs + [...(segment ?? '')].length * perCharMs),
  ))
  const total = delays.reduce((sum, delay) => sum + delay, 0)
  if (total <= totalCapMs) return delays

  const minTotal = delays.length * minMs
  if (minTotal >= totalCapMs) {
    return delays.map(() => minMs)
  }

  const availableSlack = totalCapMs - minTotal
  const originalSlack = total - minTotal
  return delays.map(delay => (
    minMs
    + Math.floor((delay - minMs) * availableSlack / originalSlack)
  ))
}
