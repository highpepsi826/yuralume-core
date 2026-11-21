/**
 * NSFW routing carve-out — structural features that stay on the normal
 * route while the mode is active.
 *
 * A feature listed here never sees the conversation's raw text, so it
 * does not need the NSFW target's community model; leaving it on the
 * normal route keeps structured-output quality (schedule/arc/feed JSON).
 * Everything else — including features added later — stays on the NSFW
 * target. That default is fail-closed on purpose.
 *
 * Source: NSFW_ROUTING_CARVE_OUT_REFERENCE.md §5B. Grey-zone features
 * (§5C, translation / scene writers / judges / image generation) are
 * deliberately absent; do not add them without measurement.
 */
export const NSFW_STRUCTURAL_FEATURES = [
  'schedule_plan',
  'schedule_weather_drift',
  'arc_plan',
  'arc_adapt',
  'arc_season_decide',
  'arc_beat_recheck',
  'arc_completion_memory',
  'feed_compose',
  'feed_comment_reply',
  'memory_consolidate',
  'goal_review',
] as const

export type NsfwStructuralFeature = (typeof NSFW_STRUCTURAL_FEATURES)[number]

/** Ticks every recommended feature, keeping any extra custom key the
 * operator already added. */
export function applyRecommendedStructuralFeatures(
  current: readonly string[],
): string[] {
  const merged = new Set<string>(current)
  for (const key of NSFW_STRUCTURAL_FEATURES) merged.add(key)
  return [
    ...NSFW_STRUCTURAL_FEATURES.filter((key) => merged.has(key)),
    ...current.filter(
      (key) => !(NSFW_STRUCTURAL_FEATURES as readonly string[]).includes(key),
    ),
  ]
}

/** Toggles one key, preserving the canonical order of the known list. */
export function toggleStructuralFeature(
  current: readonly string[],
  key: string,
  checked: boolean,
): string[] {
  const next = new Set(current)
  if (checked) next.add(key)
  else next.delete(key)
  return orderStructuralFeatures([...next])
}

/** Known keys in list order, then any unknown keys in their input order. */
export function orderStructuralFeatures(keys: readonly string[]): string[] {
  const present = new Set(keys)
  const ordered = NSFW_STRUCTURAL_FEATURES.filter((key) => present.has(key))
  const extras = keys.filter(
    (key) => !(NSFW_STRUCTURAL_FEATURES as readonly string[]).includes(key),
  )
  return [...ordered, ...extras]
}
