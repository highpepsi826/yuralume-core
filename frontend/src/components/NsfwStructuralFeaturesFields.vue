<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton } from '@/components/ui'
import {
  NSFW_STRUCTURAL_FEATURES,
  applyRecommendedStructuralFeatures,
  toggleStructuralFeature,
} from '@/utils/nsfwStructuralFeatures'

/** Editor for the NSFW target's carve-out list.
 *
 * A ticked feature stays on the normal route while the mode is active.
 * Everything else — including features added later — stays on the NSFW
 * target, so the default (all unticked) is the pre-feature behaviour.
 * See NSFW_ROUTING_CARVE_OUT_REFERENCE.md §5–6.
 */
const props = defineProps<{
  modelValue: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
}>()

const { t } = useI18n()

const selected = computed(() => new Set(props.modelValue))

function isChecked(key: string): boolean {
  return selected.value.has(key)
}

function onToggle(key: string, checked: boolean): void {
  emit('update:modelValue', toggleStructuralFeature(props.modelValue, key, checked))
}

function applyRecommended(): void {
  emit('update:modelValue', applyRecommendedStructuralFeatures(props.modelValue))
}

function clearAll(): void {
  emit('update:modelValue', [])
}
</script>

<template>
  <details class="carve-out" :open="modelValue.length > 0">
    <summary class="carve-out-summary">
      {{ t('nsfwModeTargetSetting.structuralFeatures.title') }}
      <span class="carve-out-count">
        {{ t('nsfwModeTargetSetting.structuralFeatures.selectedCount', {
          count: modelValue.length,
        }) }}
      </span>
    </summary>
    <p class="carve-out-hint">
      {{ t('nsfwModeTargetSetting.structuralFeatures.hint') }}
    </p>
    <p class="carve-out-hint is-warning">
      {{ t('nsfwModeTargetSetting.structuralFeatures.consequenceHint') }}
    </p>
    <div class="carve-out-grid">
      <label
        v-for="key in NSFW_STRUCTURAL_FEATURES"
        :key="key"
        class="carve-out-option"
      >
        <input
          type="checkbox"
          :checked="isChecked(key)"
          :disabled="disabled"
          @change="onToggle(key, ($event.target as HTMLInputElement).checked)"
        />
        <span>{{ t(`nsfwModeTargetSetting.structuralFeatures.features.${key}`) }}</span>
        <code class="carve-out-key">{{ key }}</code>
      </label>
    </div>
    <div class="carve-out-actions">
      <UiButton :disabled="disabled" @click="applyRecommended">
        {{ t('nsfwModeTargetSetting.structuralFeatures.actions.applyRecommended') }}
      </UiButton>
      <UiButton :disabled="disabled || modelValue.length === 0" @click="clearAll">
        {{ t('nsfwModeTargetSetting.structuralFeatures.actions.clear') }}
      </UiButton>
    </div>
  </details>
</template>

<style scoped>
.carve-out {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.carve-out-summary {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.carve-out-count {
  border: 1px solid var(--color-border, #2f3550);
  border-radius: 999px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 16px;
}

.carve-out-hint {
  margin: 0;
  line-height: 1.45;
}

.carve-out-hint.is-warning {
  color: #e0b341;
}

.carve-out-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 12px;
}

.carve-out-option {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.carve-out-key {
  color: var(--color-text-secondary);
  opacity: 0.7;
  font-size: 11px;
}

.carve-out-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 820px) {
  .carve-out-grid {
    grid-template-columns: 1fr;
  }
}
</style>
