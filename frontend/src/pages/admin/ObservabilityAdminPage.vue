<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { Character } from '@/types/character'
import { listCharacters } from '@/utils/api/characters'
import ObservabilityPanel from '@/components/observability/ObservabilityPanel.vue'
import { UiButton, UiCard, UiSelect, UiBadge } from '@/components/ui'
import { downloadDiagnosticExport, getDiagnosticStatus, type DiagnosticExportType, type DiagnosticExportFile, type DiagnosticStatus } from '@/utils/api/observability'

const { t } = useI18n()

// 觀測頁需要綁定一個 character context 才能拉出 funnel / emotion 資料。
// 進站若 URL 帶 ?character= 就沿用；否則挑第一個角色 (若有)。null = 全域觀測。
const route = useRoute()
const router = useRouter()

const characters = ref<Character[]>([])
const selected = ref<string>('')
const loadError = ref<string | null>(null)
const exportNow = new Date()
const exportSince = ref(toDateTimeLocal(new Date(exportNow.getTime() - 60 * 60 * 1000)))
const exportUntil = ref(toDateTimeLocal(exportNow))
const exportIncludePrompt = ref(false)
const exportIncludeMessages = ref(false)
const exportIncludeLogs = ref(false)
const exportIncludeStorageMetadata = ref(false)
const exportPreset = ref<DiagnosticExportType>('quick')
const exportBusy = ref(false)
const exportError = ref<string | null>(null)
const exportResult = ref<Pick<DiagnosticExportFile, 'filename' | 'diagnostics'> | null>(null)
const diagnosticStatus = ref<DiagnosticStatus | null>(null)
const statusError = ref(false)
const statusBusy = ref(false)

async function refreshDiagnosticStatus() {
  statusBusy.value = true
  statusError.value = false
  try {
    diagnosticStatus.value = await getDiagnosticStatus()
  } catch {
    diagnosticStatus.value = null
    statusError.value = true
  } finally {
    statusBusy.value = false
  }
}

function statusLabel(value?: string | null): string {
  const known = ['ok', 'degraded', 'unavailable', 'complete', 'partial', 'sufficient', 'insufficient', 'unknown']
  return known.includes(value || '') ? t(`admin.page.observability.states.${value}`) : t('admin.page.observability.states.unknown')
}

function formatBytes(value: number | null): string {
  return value === null ? t('admin.page.observability.states.unknown') : `${(value / 1024 / 1024).toFixed(1)} MiB`
}

async function exportDiagnostic() {
  if (!selected.value || exportBusy.value) return
  exportBusy.value = true
  exportError.value = null
  exportResult.value = null
  try {
    const exportFile = await downloadDiagnosticExport({
      characterId: selected.value,
      incidentType: exportPreset.value,
      since: toIsoInstant(exportSince.value),
      until: toIsoInstant(exportUntil.value),
      includePrompt: exportIncludePrompt.value,
      includeMessages: exportIncludeMessages.value,
      includeLogs: exportIncludeLogs.value,
      includeStorageMetadata: exportIncludeStorageMetadata.value,
    })
    const url = URL.createObjectURL(exportFile.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = exportFile.filename
    anchor.click()
    URL.revokeObjectURL(url)
    exportResult.value = { filename: exportFile.filename, diagnostics: exportFile.diagnostics }
    void refreshDiagnosticStatus()
  } catch (err) {
    exportError.value = err instanceof Error ? err.message : t('admin.page.observability.exportFailed')
  } finally {
    exportBusy.value = false
  }
}

function applyPreset(value: DiagnosticExportType) {
  exportPreset.value = value
  // Sensitive content remains an explicit checkbox choice for every preset.
  exportIncludeLogs.value = value === 'full'
  exportIncludeStorageMetadata.value = value === 'full'
}

function toIsoInstant(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

function toDateTimeLocal(value: Date): string {
  const offset = value.getTimezoneOffset()
  const local = new Date(value.getTime() - offset * 60 * 1000)
  return local.toISOString().slice(0, 16)
}

onMounted(async () => {
  void refreshDiagnosticStatus()
  try {
    characters.value = await listCharacters()
    const qsChar = typeof route.query.character === 'string' ? route.query.character : ''
    if (qsChar && characters.value.some(c => c.id === qsChar)) {
      selected.value = qsChar
    } else if (characters.value.length > 0) {
      selected.value = characters.value[0].id
    }
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : t('common.errors.loadFailed', { reason: t('common.errors.unknown') })
  }
})

watch(selected, (next) => {
  // 把選擇寫回 URL，方便分享或重新整理保留 context。
  router.replace({ query: { ...route.query, character: next || undefined } })
})
</script>

<template>
  <div class="observability-admin">
    <header class="observability-admin__header">
      <div>
        <h1>{{ t('admin.page.observability.title') }}</h1>
        <p class="observability-admin__subtitle">
          {{ t('admin.page.observability.subtitle') }}
        </p>
      </div>
      <UiBadge variant="primary">{{ t('admin.page.observability.badge') }}</UiBadge>
    </header>

    <UiCard size="lg">
      <template #header>
        <h2 class="observability-admin__card-title">{{ t('admin.page.observability.contextTitle') }}</h2>
      </template>

      <div v-if="loadError" class="observability-admin__error">
        {{ t('admin.selector.errors.loadCharactersFailedWithReason', { reason: loadError }) }}
      </div>

      <div v-else-if="characters.length === 0" class="observability-admin__hint">
        {{ t('admin.page.observability.noCharacters') }}
      </div>

      <UiSelect
        v-else
        v-model="selected"
        :label="t('admin.page.observability.targetLabel')"
        :hint="t('admin.page.observability.targetHint')"
        :options="characters.map(c => ({ value: c.id, label: c.name }))"
      />
    </UiCard>

    <UiCard v-if="selected" size="lg">
      <template #header>
        <h2 class="observability-admin__card-title">{{ t('admin.page.observability.diagnosticTitle') }}</h2>
      </template>
      <p class="observability-admin__hint">{{ t('admin.page.observability.diagnosticHint') }}</p>
      <div class="observability-admin__export-fields">
        <label>{{ t('admin.page.observability.presetLabel') }}
          <select v-model="exportPreset" @change="applyPreset(exportPreset)">
            <option value="quick">{{ t('admin.page.observability.presetQuick') }}</option>
            <option value="standard">{{ t('admin.page.observability.presetStandard') }}</option>
            <option value="full">{{ t('admin.page.observability.presetFull') }}</option>
          </select>
        </label>
        <label>{{ t('admin.page.observability.sinceLabel') }} <input v-model="exportSince" type="datetime-local" /></label>
        <label>{{ t('admin.page.observability.untilLabel') }} <input v-model="exportUntil" type="datetime-local" /></label>
        <label class="observability-admin__checkbox"><input v-model="exportIncludePrompt" type="checkbox" /> {{ t('admin.page.observability.includePrompt') }}</label>
        <label class="observability-admin__checkbox"><input v-model="exportIncludeMessages" type="checkbox" /> {{ t('admin.page.observability.includeMessages') }}</label>
        <label class="observability-admin__checkbox"><input v-model="exportIncludeLogs" type="checkbox" /> {{ t('admin.page.observability.includeLogs') }}</label>
        <label class="observability-admin__checkbox"><input v-model="exportIncludeStorageMetadata" type="checkbox" /> {{ t('admin.page.observability.includeStorageMetadata') }}</label>
      </div>
      <p class="observability-admin__hint">{{ t('admin.page.observability.sensitiveHint') }}</p>
      <p v-if="exportError" class="observability-admin__error">{{ exportError }}</p>
      <UiButton size="sm" variant="primary" :loading="exportBusy" @click="exportDiagnostic">
        {{ t('admin.page.observability.exportAction') }}
      </UiButton>
      <div v-if="exportResult" class="observability-admin__result" role="status">
        <p>{{ t('admin.page.observability.downloaded', { filename: exportResult.filename }) }}</p>
        <p>{{ t('admin.page.observability.completeness', { collection: statusLabel(exportResult.diagnostics?.collection), coverage: statusLabel(exportResult.diagnostics?.coverage) }) }}</p>
        <p v-if="exportResult.diagnostics?.missingSources.length">{{ t('admin.page.observability.missingSources', { sources: exportResult.diagnostics.missingSources.join(', ') }) }}</p>
        <p>{{ t('admin.page.observability.manifestHint', { version: exportResult.diagnostics?.manifestVersion || t('admin.page.observability.states.unknown') }) }}</p>
      </div>
    </UiCard>

    <UiCard size="lg">
      <template #header><h2 class="observability-admin__card-title">{{ t('admin.page.observability.persistenceTitle') }}</h2></template>
      <UiButton size="sm" :loading="statusBusy" @click="refreshDiagnosticStatus">{{ t('admin.page.observability.refreshStatus') }}</UiButton>
      <p v-if="statusError" class="observability-admin__error" role="status">{{ t('admin.page.observability.statusUnavailable') }}</p>
      <div v-if="diagnosticStatus" class="observability-admin__hint">
        <p>{{ t('admin.page.observability.persistenceState', { state: statusLabel(diagnosticStatus.status), enabled: diagnosticStatus.enabled ? t('admin.page.observability.states.yes') : t('admin.page.observability.states.no'), running: diagnosticStatus.running ? t('admin.page.observability.states.yes') : t('admin.page.observability.states.no') }) }}</p>
        <p>{{ t('admin.page.observability.capacity', { used: formatBytes(diagnosticStatus.logical_bytes), soft: formatBytes(diagnosticStatus.soft_limit_bytes), hard: formatBytes(diagnosticStatus.hard_limit_bytes) }) }}</p>
        <p>{{ t('admin.page.observability.retention', { info: diagnosticStatus.retention_days.info, error: diagnosticStatus.retention_days.error }) }}</p>
        <p>{{ t('admin.page.observability.persistenceGaps', { queue: diagnosticStatus.queue_depth, dropped: diagnosticStatus.dropped_count, failed: diagnosticStatus.persist_failed_count, last: diagnosticStatus.last_persisted_at || t('admin.page.observability.states.unknown') }) }}</p>
        <p>{{ t('admin.page.observability.cleanup', { last: diagnosticStatus.housekeeping.last_succeeded_at || t('admin.page.observability.states.unknown'), count: diagnosticStatus.housekeeping.deleted_rows }) }}</p>
        <p v-if="diagnosticStatus.housekeeping.last_error || diagnosticStatus.reason" class="observability-admin__error">{{ t('admin.page.observability.persistenceIssue', { reason: diagnosticStatus.housekeeping.last_error || diagnosticStatus.reason }) }}</p>
      </div>
      <p class="observability-admin__hint">{{ t('admin.page.observability.capacityHint') }}</p>
    </UiCard>

    <ObservabilityPanel
      v-if="selected"
      :character-id="selected"
      :characters="characters.map(c => ({ id: c.id, name: c.name }))"
    />
  </div>
</template>

<style scoped>
.observability-admin {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 1100px;
}
.observability-admin__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}
.observability-admin__header h1 {
  margin: 0 0 var(--space-1);
  font-size: var(--font-xl);
}
.observability-admin__subtitle {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
}
.observability-admin__card-title {
  margin: 0;
  font-size: var(--font-md);
  font-weight: 600;
}
.observability-admin__error {
  color: #f4a3a3;
  font-size: var(--font-sm);
}
.observability-admin__hint {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
}
.observability-admin__export-fields {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: end;
  margin: var(--space-3) 0;
}
.observability-admin__export-fields label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}
.observability-admin__export-fields input[type="datetime-local"] {
  min-height: 36px;
  padding: 0 var(--space-2);
  color: var(--color-text-primary);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}
.observability-admin__checkbox {
  flex-direction: row !important;
  align-items: center;
  min-height: 36px;
}
.observability-admin__result {
  margin-top: var(--space-3);
  font-size: var(--font-sm);
  overflow-wrap: anywhere;
}
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: var(--font-xs);
}
</style>
