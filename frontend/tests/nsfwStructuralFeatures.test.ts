import { describe, expect, it } from 'vitest'
import {
  NSFW_STRUCTURAL_FEATURES,
  applyRecommendedStructuralFeatures,
  orderStructuralFeatures,
  toggleStructuralFeature,
} from '@/utils/nsfwStructuralFeatures'

describe('nsfwStructuralFeatures', () => {
  it('ships the eleven approved carve-out keys', () => {
    expect(NSFW_STRUCTURAL_FEATURES).toHaveLength(11)
    expect(NSFW_STRUCTURAL_FEATURES).toContain('schedule_plan')
    expect(NSFW_STRUCTURAL_FEATURES).toContain('goal_review')
  })

  it('keeps grey-zone keys out', () => {
    for (const key of [
      'chat',
      'post_turn',
      'arc_scene_write',
      'story_scene_close',
      'chat_assist',
      'prompt_rewrite',
      'tts_translate',
      'image_feed',
      'video_storyboard',
      'outcome_claim_judge',
    ]) {
      expect(NSFW_STRUCTURAL_FEATURES as readonly string[]).not.toContain(key)
    }
  })

  it('recommended set ticks everything and keeps custom extras', () => {
    expect(applyRecommendedStructuralFeatures([])).toEqual([
      ...NSFW_STRUCTURAL_FEATURES,
    ])
    expect(applyRecommendedStructuralFeatures(['schedule_plan', 'my_custom'])).toEqual([
      ...NSFW_STRUCTURAL_FEATURES,
      'my_custom',
    ])
  })

  it('toggles keep canonical order and drop unchecked keys', () => {
    expect(toggleStructuralFeature([], 'arc_plan', true)).toEqual(['arc_plan'])
    expect(
      toggleStructuralFeature(['goal_review', 'arc_plan'], 'schedule_plan', true),
    ).toEqual(['schedule_plan', 'arc_plan', 'goal_review'])
    expect(toggleStructuralFeature(['schedule_plan'], 'schedule_plan', false)).toEqual([])
  })

  it('orders unknown keys after known ones', () => {
    expect(orderStructuralFeatures(['zzz', 'feed_compose', 'aaa'])).toEqual([
      'feed_compose',
      'zzz',
      'aaa',
    ])
  })
})
