<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { UiBadge, UiButton, UiSection, UiTextarea } from '@/components/ui'
import {
  deleteAdminPromptTemplateDraft,
  getAdminPromptTemplate,
  listAdminPromptTemplates,
  publishAdminPromptTemplateDraft,
  putAdminPromptTemplateDraft,
  type PromptTemplate,
  type PromptTemplateSummary,
} from '@/utils/api/promptCustomizations'

const templates = ref<PromptTemplateSummary[]>([])
const selected = ref<PromptTemplate | null>(null)
const draft = ref('')
const loading = ref(true)
const saving = ref(false)
const feedback = ref('')
const selectedName = computed(() => selected.value?.name ?? '')
const categories = computed(() => [...new Set(templates.value.map((item) => item.category))])
const showDiff = ref(false)

async function selectTemplate(name: string) {
  feedback.value = ''
  try {
    selected.value = await getAdminPromptTemplate(name)
    draft.value = selected.value.draft_content || selected.value.content
    showDiff.value = false
  } catch (error) { feedback.value = error instanceof Error ? error.message : '無法讀取 prompt。' }
}

async function refresh() {
  templates.value = await listAdminPromptTemplates()
  if (selected.value) await selectTemplate(selected.value.name)
}

async function load() {
  loading.value = true
  try {
    templates.value = await listAdminPromptTemplates()
    if (templates.value[0]) await selectTemplate(templates.value[0].name)
  } catch (error) { feedback.value = error instanceof Error ? error.message : '無法讀取設定。' }
  finally { loading.value = false }
}

async function saveDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try { await putAdminPromptTemplateDraft(selected.value.name, draft.value); await refresh(); feedback.value = 'Draft 已儲存，尚未影響所有玩家。' }
  catch (error) { feedback.value = error instanceof Error ? error.message : '儲存 Draft 失敗。' }
  finally { saving.value = false }
}
async function publishDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try { await publishAdminPromptTemplateDraft(selected.value.name); await refresh(); feedback.value = 'Draft 已正式發布；各服務約 10 秒內套用。' }
  catch (error) { feedback.value = error instanceof Error ? error.message : '發布 Draft 失敗。' }
  finally { saving.value = false }
}
async function discardDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try { await deleteAdminPromptTemplateDraft(selected.value.name); await refresh(); feedback.value = 'Draft 已捨棄。' }
  catch (error) { feedback.value = error instanceof Error ? error.message : '捨棄 Draft 失敗。' }
  finally { saving.value = false }
}
function loadPublished() { if (selected.value) draft.value = selected.value.content }
onMounted(load)
</script>

<template>
  <div class="prompt-admin">
    <RouterLink to="/prompt-playground?scope=admin">開啟 Playground（提示詞測試場）</RouterLink>
    <header><div><h1>Prompt Studio</h1><p>先用 Draft 測試與比較，再正式發布全站版本。發布後各服務約 10 秒內套用。</p></div><UiBadge variant="primary">Admin</UiBadge></header>
    <p v-if="loading" class="prompt-admin__hint">載入中…</p>
    <template v-else>
      <UiSection v-if="selected" :title="selected.title" bordered>
        <div class="prompt-admin__meta"><UiBadge :variant="selected.has_draft ? 'warning' : selected.overridden ? 'primary' : 'default'">{{ selected.has_draft ? '有 Draft' : selected.overridden ? '已發布覆寫' : '內建預設' }}</UiBadge><UiBadge v-if="selected.important" variant="danger">重要 prompt</UiBadge></div>
        <p :class="selected.important ? 'prompt-admin__warning' : 'prompt-admin__hint'">{{ selected.important ? `重要 prompt，改了會影響：${selected.impact}` : selected.impact }}</p>
        <p class="prompt-admin__hint">必須保留的變數：{{ selected.variables.length ? selected.variables.map((name) => `$${name}`).join('、') : '無' }}</p>
        <UiTextarea v-model="draft" :rows="18" :maxlength="24000" label="Draft" />
        <div class="prompt-admin__actions">
          <UiButton variant="primary" :loading="saving" @click="saveDraft">儲存 Draft</UiButton>
          <UiButton variant="secondary" :disabled="saving || !selected.has_draft" @click="publishDraft">正式發布 Draft</UiButton>
          <UiButton variant="ghost" :disabled="saving || !selected.has_draft" @click="draft = selected.draft_content">載入 Draft</UiButton>
          <UiButton variant="ghost" :disabled="saving" @click="loadPublished">檢視已發布版本</UiButton>
          <UiButton variant="ghost" :disabled="!selected.has_draft" @click="showDiff = !showDiff">{{ showDiff ? '收起差異' : '查看差異' }}</UiButton>
          <UiButton variant="ghost" :disabled="saving || !selected.has_draft" @click="discardDraft">捨棄 Draft</UiButton>
        </div>
        <details v-if="showDiff && selected.has_draft" open class="prompt-admin__diff"><summary>已發布版本</summary><pre>{{ selected.content }}</pre><summary>Draft</summary><pre>{{ selected.draft_content }}</pre></details>
      </UiSection>
      <UiSection v-for="category in categories" :key="category" :title="category" bordered><div class="prompt-admin__templates"><UiButton v-for="template in templates.filter((item) => item.category === category)" :key="template.name" size="sm" :variant="template.name === selectedName ? 'primary' : 'secondary'" :active="template.name === selectedName" @click="selectTemplate(template.name)">{{ template.has_draft ? `${template.title} [Draft]` : template.title }}</UiButton></div></UiSection>
    </template>
    <p v-if="feedback" class="prompt-admin__feedback">{{ feedback }}</p>
  </div>
</template>

<style scoped>
.prompt-admin { display: flex; flex-direction: column; gap: 16px; }
.prompt-admin header, .prompt-admin__meta, .prompt-admin__actions, .prompt-admin__templates { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.prompt-admin header, .prompt-admin__meta { justify-content: space-between; }
.prompt-admin h1, .prompt-admin p { margin: 0; }
.prompt-admin header p, .prompt-admin__hint, .prompt-admin__feedback { color: var(--color-text-secondary); margin-top: 4px; line-height: 1.55; }
.prompt-admin__warning { color: #e9bb72; line-height: 1.55; }
.prompt-admin__diff { border-top: 1px solid var(--color-border); padding-top: 8px; }
.prompt-admin__diff pre { max-height: 280px; overflow: auto; white-space: pre-wrap; font-size: var(--font-xs); }
</style>
