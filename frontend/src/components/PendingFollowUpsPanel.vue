<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createScheduledPromise,
  deleteScheduledPromise,
  listAdminPendingFollowUps,
  triggerPendingFollowUpTick,
  updateScheduledPromise,
  type AdminPendingFollowUp,
  type PendingFollowUp,
} from '@/utils/api/pendingFollowUps'
import { useTimezone } from '@/composables/useTimezone'
import { formatDateTime } from '@/i18n/formatters'
import { UiButton } from '@/components/ui'

const props = defineProps<{
  characterId: string | null
}>()

const { locale, t } = useI18n()
const { timeZone } = useTimezone()

const rows = ref<AdminPendingFollowUp[]>([])
const loading = ref(false)
const errorMsg = ref<string | null>(null)
const tickBusy = ref(false)
const tickMsg = ref<string | null>(null)
const createOpen = ref(false)
const createBusy = ref(false)
const createError = ref<string | null>(null)
const createScheduledFor = ref('')
const createIntent = ref('')
const editingId = ref<string | null>(null)
const editBusy = ref(false)
const editError = ref<string | null>(null)
const editScheduledFor = ref('')
const editIntent = ref('')

function errorReason(err: unknown): string {
  const response = (err as {
    response?: { data?: { detail?: unknown } }
  })?.response
  const detail = response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return err instanceof Error ? err.message : t('pendingFollowUpsPanel.errors.unknown')
}

function localDateTimeInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function defaultScheduledFor(): string {
  const next = new Date(Date.now() + 60 * 60 * 1000)
  next.setSeconds(0, 0)
  return localDateTimeInput(next)
}

function toIso(value: string): string | null {
  const parsed = new Date(value)
  if (!value || Number.isNaN(parsed.getTime())) return null
  return parsed.toISOString()
}

async function reload() {
  if (!props.characterId) {
    rows.value = []
    return
  }
  loading.value = true
  errorMsg.value = null
  try {
    rows.value = await listAdminPendingFollowUps(props.characterId)
  } catch (err) {
    errorMsg.value = errorReason(err)
    rows.value = []
  } finally {
    loading.value = false
  }
}

function isEditable(row: AdminPendingFollowUp): boolean {
  return row.kind === 'scheduled_promise' && row.status === 'queued'
}

function openCreate() {
  createError.value = null
  createScheduledFor.value = defaultScheduledFor()
  createIntent.value = ''
  createOpen.value = true
}

function closeCreate() {
  if (!createBusy.value) createOpen.value = false
}

async function submitCreate() {
  if (createBusy.value || !props.characterId) return
  const scheduled = toIso(createScheduledFor.value)
  const intent = createIntent.value.trim()
  if (!scheduled || !intent) {
    createError.value = t('pendingFollowUpsPanel.errors.createFieldsRequired')
    return
  }
  createBusy.value = true
  createError.value = null
  try {
    await createScheduledPromise({
      character_id: props.characterId,
      scheduled_for: scheduled,
      promise_intent: intent,
    })
    createOpen.value = false
    await reload()
  } catch (err) {
    createError.value = errorReason(err)
  } finally {
    createBusy.value = false
  }
}

function beginEdit(row: AdminPendingFollowUp) {
  if (!isEditable(row)) return
  editingId.value = row.id
  editError.value = null
  editScheduledFor.value = localDateTimeInput(new Date(row.scheduled_for))
  editIntent.value = row.promise_intent
}

function cancelEdit() {
  if (!editBusy.value) {
    editingId.value = null
    editError.value = null
  }
}

async function submitEdit(row: AdminPendingFollowUp) {
  if (editBusy.value || !isEditable(row)) return
  const scheduled = toIso(editScheduledFor.value)
  const intent = editIntent.value.trim()
  if (!scheduled || !intent) {
    editError.value = t('pendingFollowUpsPanel.errors.editFieldsRequired')
    return
  }
  editBusy.value = true
  editError.value = null
  try {
    await updateScheduledPromise(row.id, {
      scheduled_for: scheduled,
      promise_intent: intent,
    })
    editingId.value = null
    await reload()
  } catch (err) {
    editError.value = errorReason(err)
  } finally {
    editBusy.value = false
  }
}

async function removeRow(row: AdminPendingFollowUp) {
  if (
    !isEditable(row)
    || !window.confirm(t('pendingFollowUpsPanel.actions.deleteConfirm'))
  ) return
  try {
    await deleteScheduledPromise(row.id)
    if (editingId.value === row.id) editingId.value = null
    await reload()
  } catch (err) {
    errorMsg.value = errorReason(err)
  }
}

async function handleTickNow() {
  if (tickBusy.value) return
  tickBusy.value = true
  tickMsg.value = null
  try {
    const result = await triggerPendingFollowUpTick()
    tickMsg.value = result.resolved > 0
      ? t('pendingFollowUpsPanel.tick.released', { count: result.resolved })
      : t('pendingFollowUpsPanel.tick.none')
    await reload()
  } catch (err) {
    tickMsg.value = t('pendingFollowUpsPanel.tick.failedWithReason', {
      reason: errorReason(err),
    })
  } finally {
    tickBusy.value = false
    // Auto-clear the toast after a few seconds so it doesn't linger.
    setTimeout(() => { tickMsg.value = null }, 5000)
  }
}

function formatRelative(iso: string): string {
  const date = new Date(iso)
  const diffMs = date.getTime() - Date.now()
  const absSec = Math.abs(diffMs) / 1000
  const future = diffMs > 0
  if (absSec < 60) return future
    ? t('pendingFollowUpsPanel.relative.imminent')
    : t('pendingFollowUpsPanel.relative.justNow')
  if (absSec < 3600) {
    const value = Math.round(absSec / 60)
    return future
      ? t('pendingFollowUpsPanel.relative.minutesAhead', { count: value })
      : t('pendingFollowUpsPanel.relative.minutesAgo', { count: value })
  }
  if (absSec < 86400) {
    const value = Math.round(absSec / 3600)
    return future
      ? t('pendingFollowUpsPanel.relative.hoursAhead', { count: value })
      : t('pendingFollowUpsPanel.relative.hoursAgo', { count: value })
  }
  const value = Math.round(absSec / 86400)
  return future
    ? t('pendingFollowUpsPanel.relative.daysAhead', { count: value })
    : t('pendingFollowUpsPanel.relative.daysAgo', { count: value })
}

function formatAbsolute(iso: string): string {
  return formatDateTime(iso, locale.value, timeZone.value)
}

const hasRows = computed(() => rows.value.length > 0)

function statusLabel(status: PendingFollowUp['status']): string {
  return t(`pendingFollowUpsPanel.status.${status}`)
}

watch(() => props.characterId, () => {
  editingId.value = null
  editError.value = null
  createOpen.value = false
  void reload()
}, { immediate: true })

// Light polling so the user sees status flip from queued → resolved
// without a manual refresh.
let pollTimer: ReturnType<typeof setInterval> | null = null
watch(() => props.characterId, (id) => {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (id) {
    pollTimer = setInterval(() => { void reload() }, 15000)
  }
}, { immediate: true })
onBeforeUnmount(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
})
</script>

<template>
  <section class="pending-followups-panel">
    <header class="panel-header">
      <div>
        <h3 class="section-title">{{ t('pendingFollowUpsPanel.title') }}</h3>
        <p class="panel-hint">
          {{ t('pendingFollowUpsPanel.hint') }}
        </p>
      </div>
      <div class="panel-actions">
        <UiButton
          size="sm"
          :loading="loading"
          :disabled="!characterId"
          @click="reload"
        >{{ t('pendingFollowUpsPanel.actions.refresh') }}</UiButton>
        <UiButton
          size="sm"
          variant="primary"
          :disabled="!characterId || createBusy"
          @click="createOpen ? closeCreate() : openCreate()"
        >{{ createOpen
          ? t('pendingFollowUpsPanel.actions.cancelCreate')
          : t('pendingFollowUpsPanel.actions.addPromise') }}</UiButton>
        <UiButton
          size="sm"
          :loading="tickBusy"
          :title="t('pendingFollowUpsPanel.actions.tickTitle')"
          @click="handleTickNow"
        >{{ t('pendingFollowUpsPanel.actions.tickNow') }}</UiButton>
      </div>
    </header>

    <div v-if="tickMsg" class="panel-toast">{{ tickMsg }}</div>
    <div v-if="errorMsg" class="panel-error">{{ errorMsg }}</div>

    <form v-if="createOpen" class="promise-form create-form" @submit.prevent="submitCreate">
      <div class="form-title">{{ t('pendingFollowUpsPanel.create.title') }}</div>
      <div class="form-grid">
        <label class="field-small">
          <span class="field-label">{{ t('pendingFollowUpsPanel.create.timeLabel') }}</span>
          <input
            v-model="createScheduledFor"
            class="field-input"
            type="datetime-local"
            required
            :disabled="createBusy"
          />
        </label>
        <label class="field-small field-wide">
          <span class="field-label">{{ t('pendingFollowUpsPanel.create.intentLabel') }}</span>
          <textarea
            v-model="createIntent"
            class="field-textarea"
            rows="2"
            maxlength="500"
            required
            :placeholder="t('pendingFollowUpsPanel.create.intentPlaceholder')"
            :disabled="createBusy"
          />
        </label>
      </div>
      <p class="form-hint">{{ t('pendingFollowUpsPanel.create.hint') }}</p>
      <div v-if="createError" class="form-error" role="alert">{{ createError }}</div>
      <div class="form-actions">
        <UiButton type="button" size="sm" :disabled="createBusy" @click="closeCreate">
          {{ t('common.actions.cancel') }}
        </UiButton>
        <UiButton type="submit" size="sm" variant="primary" :loading="createBusy">
          {{ t('pendingFollowUpsPanel.actions.save') }}
        </UiButton>
      </div>
    </form>

    <div v-if="!characterId" class="panel-empty">{{ t('pendingFollowUpsPanel.empty.selectCharacter') }}</div>
    <div v-else-if="loading && !hasRows" class="panel-empty">{{ t('common.state.loading') }}</div>
    <div v-else-if="!hasRows" class="panel-empty">
      {{ t('pendingFollowUpsPanel.empty.none') }}<br />
      {{ t('pendingFollowUpsPanel.empty.noneHint') }}
    </div>

    <ul v-else class="row-list">
      <li
        v-for="row in rows"
        :key="row.id"
        :class="['row-card', `status-${row.status}`]"
      >
        <div class="row-head">
          <span :class="['status-pill', `pill-${row.status}`]">
            {{ statusLabel(row.status) }}
          </span>
          <span v-if="row.defer_reason" class="reason-pill">
            {{ row.defer_reason }}
          </span>
          <span class="time-pill" :title="formatAbsolute(row.scheduled_for)">
            {{ t('pendingFollowUpsPanel.scheduledFor', { relative: formatRelative(row.scheduled_for) }) }}
          </span>
          <span v-if="row.kind === 'scheduled_promise'" class="kind-pill">
            {{ t('pendingFollowUpsPanel.kind.scheduledPromise') }}
          </span>
          <span v-else class="kind-pill">
            {{ t('pendingFollowUpsPanel.kind.busyDefer') }}
          </span>
        </div>

        <div v-if="row.kind === 'scheduled_promise'" class="promise-intent">
          <div class="brief-label">{{ t('pendingFollowUpsPanel.promiseIntentLabel') }}</div>
          <div class="brief-text">{{ row.promise_intent }}</div>
        </div>

        <div class="brief">
          <div class="brief-label">{{ t('pendingFollowUpsPanel.briefLabel') }}</div>
          <div class="brief-text">{{ row.brief_reply }}</div>
        </div>

        <div class="queued-messages">
          <div class="queued-label">
            {{ t('pendingFollowUpsPanel.queuedMessages', { count: row.messages.length }) }}
          </div>
          <ul class="msg-list">
            <li v-for="(msg, idx) in row.messages" :key="idx" class="msg-item">
              <span class="msg-bullet">·</span>
              <span class="msg-text">{{ msg.content }}</span>
              <span class="msg-time" :title="formatAbsolute(msg.queued_at)">
                {{ formatRelative(msg.queued_at) }}
              </span>
            </li>
          </ul>
        </div>

        <div v-if="row.last_error" class="row-error">
          {{ t('pendingFollowUpsPanel.lastError', { error: row.last_error }) }}
        </div>

        <div v-if="isEditable(row)" class="row-actions">
          <UiButton size="sm" @click="beginEdit(row)">
            {{ t('pendingFollowUpsPanel.actions.edit') }}
          </UiButton>
          <UiButton size="sm" variant="danger" @click="removeRow(row)">
            {{ t('pendingFollowUpsPanel.actions.delete') }}
          </UiButton>
        </div>

        <form
          v-if="editingId === row.id"
          class="promise-form edit-form"
          @submit.prevent="submitEdit(row)"
        >
          <div class="form-title">{{ t('pendingFollowUpsPanel.edit.title') }}</div>
          <label class="field-small">
            <span class="field-label">{{ t('pendingFollowUpsPanel.edit.timeLabel') }}</span>
            <input
              v-model="editScheduledFor"
              class="field-input"
              type="datetime-local"
              required
              :disabled="editBusy"
            />
          </label>
          <label class="field-small">
            <span class="field-label">{{ t('pendingFollowUpsPanel.edit.intentLabel') }}</span>
            <textarea
              v-model="editIntent"
              class="field-textarea"
              rows="2"
              maxlength="500"
              required
              :disabled="editBusy"
            />
          </label>
          <p class="form-hint">{{ t('pendingFollowUpsPanel.edit.hint') }}</p>
          <div v-if="editError" class="form-error" role="alert">{{ editError }}</div>
          <div class="form-actions">
            <UiButton type="button" size="sm" :disabled="editBusy" @click="cancelEdit">
              {{ t('common.actions.cancel') }}
            </UiButton>
            <UiButton type="submit" size="sm" variant="primary" :loading="editBusy">
              {{ t('pendingFollowUpsPanel.actions.save') }}
            </UiButton>
          </div>
        </form>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.pending-followups-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.section-title {
  margin: 0 0 4px 0;
  font-size: 15px;
  font-weight: 600;
}

.panel-hint {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary, #888);
  line-height: 1.5;
  max-width: 360px;
}

.panel-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.panel-toast {
  padding: 8px 12px;
  font-size: 12px;
  background: rgba(64, 158, 255, 0.08);
  color: #2c70b8;
  border-radius: 6px;
}

.panel-error {
  padding: 8px 12px;
  font-size: 12px;
  background: rgba(245, 108, 108, 0.08);
  color: #c0392b;
  border-radius: 6px;
}

.promise-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 8px;
  background: var(--color-bg-secondary, #fafafa);
}

.create-form {
  border-color: rgba(64, 158, 255, 0.35);
}

.form-title {
  font-size: 13px;
  font-weight: 600;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.75fr) minmax(220px, 1.25fr);
  gap: 10px;
}

.field-small {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.field-wide {
  min-width: 0;
}

.field-label {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
}

.field-input,
.field-textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: 5px;
  padding: 7px 8px;
  color: var(--color-text, #222);
  background: var(--color-bg, #fff);
  font: inherit;
  font-size: 13px;
}

.field-textarea {
  resize: vertical;
  min-height: 58px;
}

.form-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-secondary, #888);
}

.form-error {
  color: #c0392b;
  font-size: 12px;
  line-height: 1.4;
}

.form-actions,
.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.panel-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-secondary, #888);
  line-height: 1.6;
  background: var(--color-bg-secondary, #fafafa);
  border-radius: 8px;
}

.row-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row-card {
  padding: 12px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 8px;
  background: var(--color-bg, #fff);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row-card.status-resolving {
  border-color: rgba(64, 158, 255, 0.4);
  background: rgba(64, 158, 255, 0.04);
}
.row-card.status-resolved {
  opacity: 0.7;
}

.row-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.status-pill,
.reason-pill,
.time-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  line-height: 1.6;
}

.pill-queued { background: #fff3cd; color: #856404; }
.pill-resolving { background: #d1ecf1; color: #0c5460; }
.pill-resolved { background: #d4edda; color: #155724; }
.pill-cancelled { background: #f8d7da; color: #721c24; }

.reason-pill { background: rgba(0, 0, 0, 0.05); color: #555; }
.time-pill { background: rgba(0, 0, 0, 0.05); color: #555; }
.kind-pill { background: rgba(183, 93, 63, 0.12); color: #8d4935; }

.brief { display: flex; flex-direction: column; gap: 2px; }
.brief-label,
.queued-label {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
}
.brief-text {
  font-size: 13px;
  padding: 6px 10px;
  background: var(--color-bg-secondary, #fafafa);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
}

.promise-intent {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.edit-form {
  margin-top: 2px;
}

.queued-messages {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.msg-list { list-style: none; padding: 0; margin: 0; }
.msg-item {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 13px;
  line-height: 1.5;
  padding: 2px 0;
}
.msg-bullet { color: var(--color-text-secondary, #888); }
.msg-text {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-time {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
  flex-shrink: 0;
}

.row-error {
  padding: 6px 10px;
  font-size: 11px;
  background: rgba(245, 108, 108, 0.08);
  color: #c0392b;
  border-radius: 4px;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions,
  .row-actions {
    justify-content: stretch;
  }

  .form-actions :deep(button),
  .row-actions :deep(button) {
    flex: 1 1 auto;
  }
}
</style>
