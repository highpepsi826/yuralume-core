<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Character, InitialRelationshipPayload } from '@/types/character'
import { UiButton } from '@/components/ui'
import InitialRelationshipWizardModal from './InitialRelationshipWizardModal.vue'
import {
  getInitialRelationship,
  updateInitialRelationship,
} from '@/utils/api/characters'

const props = defineProps<{
  character: Character
}>()

const { t } = useI18n()
const seed = ref<InitialRelationshipPayload | null>(null)
const loading = ref(false)
const saving = ref(false)
const editorVisible = ref(false)
const loadError = ref<string | null>(null)
const saveError = ref<string | null>(null)
const successFeedback = ref<string | null>(null)

async function load() {
  loading.value = true
  seed.value = null
  loadError.value = null
  saveError.value = null
  successFeedback.value = null
  try {
    seed.value = await getInitialRelationship(props.character.id)
  } catch (error) {
    loadError.value = error instanceof Error
      ? t('characterEdit.initialRelationship.loadFailedWithReason', { reason: error.message })
      : t('characterEdit.initialRelationship.loadFailed')
  } finally {
    loading.value = false
  }
}

function openEditor() {
  saveError.value = null
  successFeedback.value = null
  editorVisible.value = true
}

function closeEditor() {
  if (saving.value) return
  editorVisible.value = false
  saveError.value = null
}

async function save(payload: InitialRelationshipPayload | null) {
  if (!payload || saving.value) return
  saving.value = true
  saveError.value = null
  successFeedback.value = null
  try {
    seed.value = await updateInitialRelationship(props.character.id, payload)
    editorVisible.value = false
    successFeedback.value = t('characterEdit.initialRelationship.saved')
  } catch (error) {
    saveError.value = error instanceof Error
      ? t('characterEdit.initialRelationship.saveFailedWithReason', { reason: error.message })
      : t('characterEdit.initialRelationship.saveFailed')
  } finally {
    saving.value = false
  }
}

function scheduleLabel(value: string | undefined): string {
  const labels: Record<string, string> = {
    none: 'none',
    mention_only: 'mentionOnly',
    invite_required: 'inviteRequired',
    shared_allowed: 'sharedAllowed',
  }
  return t(`characterCreate.initialRelationship.scheduleOptions.${labels[value || 'none'] || 'none'}`)
}

watch(() => props.character.id, () => { void load() }, { immediate: true })
</script>

<template>
  <div class="initial-relationship-settings">
    <p v-if="loading" class="initial-relationship-settings__state">
      {{ t('characterEdit.initialRelationship.loading') }}
    </p>

    <div v-else-if="!loadError" class="initial-relationship-settings__summary">
      <div class="initial-relationship-settings__row">
        <span>{{ t('characterEdit.initialRelationship.relationshipLabel') }}</span>
        <strong>{{ seed?.relationship_label || t('characterEdit.initialRelationship.unset') }}</strong>
      </div>
      <div class="initial-relationship-settings__row">
        <span>{{ t('characterEdit.initialRelationship.scheduleLabel') }}</span>
        <strong>{{ scheduleLabel(seed?.schedule_involvement_policy) }}</strong>
      </div>
      <div class="initial-relationship-settings__row">
        <span>{{ t('characterEdit.initialRelationship.proactiveLabel') }}</span>
        <strong>
          {{ seed?.proactive_permission
            ? t('characterEdit.initialRelationship.proactiveEnabled')
            : t('characterEdit.initialRelationship.proactiveDisabled') }}
        </strong>
      </div>
    </div>

    <div class="initial-relationship-settings__actions">
      <UiButton
        v-if="loadError"
        variant="secondary"
        size="sm"
        :disabled="loading"
        @click="load"
      >
        {{ t('common.actions.retry') }}
      </UiButton>
      <UiButton
        v-else
        variant="secondary"
        size="sm"
        :disabled="loading || saving"
        @click="openEditor"
      >
        {{ seed ? t('characterEdit.initialRelationship.editAction') : t('characterEdit.initialRelationship.setAction') }}
      </UiButton>
    </div>

    <p
      v-if="loadError"
      class="initial-relationship-settings__feedback initial-relationship-settings__feedback--error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p
      v-else-if="successFeedback"
      class="initial-relationship-settings__feedback initial-relationship-settings__feedback--success"
      role="status"
    >
      {{ successFeedback }}
    </p>

    <InitialRelationshipWizardModal
      :visible="editorVisible"
      mode="edit"
      :card-name="character.name"
      :card="null"
      :initial-relationship="seed"
      :loading="saving"
      :error="saveError"
      @close="closeEditor"
      @confirm="save"
    />
  </div>
</template>

<style scoped>
.initial-relationship-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.initial-relationship-settings__state,
.initial-relationship-settings__feedback {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-xs);
  line-height: 1.55;
}

.initial-relationship-settings__summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
}

.initial-relationship-settings__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-text-secondary);
  font-size: var(--font-xs);
}

.initial-relationship-settings__row strong {
  color: var(--color-text-primary);
  font-weight: 600;
  text-align: right;
}

.initial-relationship-settings__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.initial-relationship-settings__feedback--success {
  color: #7dc49a;
}

.initial-relationship-settings__feedback--error {
  color: #fca5a5;
}
</style>
