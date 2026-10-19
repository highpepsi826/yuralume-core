<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { UiBadge, UiButton, UiTextarea } from '@/components/ui'
import {
  deletePlayerPromptTemplateDraft,
  getPlayerPromptTemplate,
  listPlayerPromptTemplates,
  publishPlayerPromptTemplateDraft,
  putPlayerPromptTemplateDraft,
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
const showDiff = ref(false)

async function selectTemplate(name: string) {
  feedback.value = ''
  try {
    selected.value = await getPlayerPromptTemplate(name)
    draft.value = selected.value.draft_content || selected.value.content
    showDiff.value = false
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取 prompt。'
  }
}

async function refresh() {
  templates.value = await listPlayerPromptTemplates()
  if (selected.value) await selectTemplate(selected.value.name)
}

async function load() {
  loading.value = true
  try {
    templates.value = await listPlayerPromptTemplates()
    if (templates.value[0]) await selectTemplate(templates.value[0].name)
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取設定。'
  } finally { loading.value = false }
}

async function saveDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try {
    await putPlayerPromptTemplateDraft(selected.value.name, draft.value)
    await refresh()
    feedback.value = 'Draft 已儲存，尚未影響目前有效版本。'
  } catch (error) { feedback.value = error instanceof Error ? error.message : '儲存 Draft 失敗。' }
  finally { saving.value = false }
}

async function publishDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try {
    await publishPlayerPromptTemplateDraft(selected.value.name)
    await refresh()
    feedback.value = 'Draft 已發布，之後的生成會使用你的新覆寫。'
  } catch (error) { feedback.value = error instanceof Error ? error.message : '發布 Draft 失敗。' }
  finally { saving.value = false }
}

async function discardDraft() {
  if (!selected.value) return
  saving.value = true; feedback.value = ''
  try {
    await deletePlayerPromptTemplateDraft(selected.value.name)
    await refresh()
    feedback.value = 'Draft 已捨棄。'
  } catch (error) { feedback.value = error instanceof Error ? error.message : '捨棄 Draft 失敗。' }
  finally { saving.value = false }
}

function loadEffective() {
  if (selected.value) draft.value = selected.value.content
}

onMounted(load)
</script>

<template>
  <div class="prompt-studio">
    <RouterLink to="/prompt-playground">開啟 Playground（提示詞測試場）</RouterLink>
    <p class="prompt-studio__hint">先儲存 Draft，再發布才會改變你的有效覆寫。角色資料、記憶、時間、行程與對話內容仍會在每次生成時動態注入；請保留 <code>$變數</code>。</p>
    <p v-if="loading" class="prompt-studio__hint">載入中…</p>
    <template v-else>
      <div class="prompt-studio__tabs" role="tablist" aria-label="可自訂 prompt">
        <UiButton v-for="template in templates" :key="template.name" size="sm" :variant="template.name === selectedName ? 'primary' : 'secondary'" :active="template.name === selectedName" @click="selectTemplate(template.name)">{{ template.title }}</UiButton>
      </div>
      <template v-if="selected">
        <div class="prompt-studio__meta"><strong>{{ selected.title }}</strong><UiBadge :variant="selected.has_draft ? 'warning' : selected.overridden ? 'primary' : 'default'">{{ selected.has_draft ? '有 Draft' : selected.overridden ? '已覆寫' : '目前預設' }}</UiBadge></div>
        <p class="prompt-studio__impact">{{ selected.impact }}</p>
        <p class="prompt-studio__variables">必須保留的變數：{{ selected.variables.length ? selected.variables.map((name) => `$${name}`).join('、') : '無' }}</p>
        <UiTextarea v-model="draft" :rows="14" :maxlength="24000" label="Draft" />
        <div class="prompt-studio__actions">
          <UiButton variant="primary" size="sm" :loading="saving" @click="saveDraft">儲存 Draft</UiButton>
          <UiButton variant="secondary" size="sm" :disabled="saving || !selected.has_draft" @click="publishDraft">發布 Draft</UiButton>
          <UiButton variant="ghost" size="sm" :disabled="saving || !selected.has_draft" @click="draft = selected.draft_content">載入 Draft</UiButton>
          <UiButton variant="ghost" size="sm" :disabled="saving" @click="loadEffective">載入目前有效版本</UiButton>
          <UiButton variant="ghost" size="sm" :disabled="!selected.has_draft" @click="showDiff = !showDiff">{{ showDiff ? '收起差異' : '查看差異' }}</UiButton>
          <UiButton variant="ghost" size="sm" :disabled="saving || !selected.has_draft" @click="discardDraft">捨棄 Draft</UiButton>
        </div>
        <details v-if="showDiff && selected.has_draft" open class="prompt-studio__diff"><summary>目前有效版本</summary><pre>{{ selected.content }}</pre><summary>Draft</summary><pre>{{ selected.draft_content }}</pre></details>
      </template>
    </template>
    <p v-if="feedback" class="prompt-studio__feedback">{{ feedback }}</p>
  </div>
</template>

<style scoped>
.prompt-studio { display: flex; flex-direction: column; gap: 10px; }
.prompt-studio__hint, .prompt-studio__impact, .prompt-studio__variables, .prompt-studio__feedback { margin: 0; color: var(--color-text-secondary); font-size: var(--font-xs); line-height: 1.55; }
.prompt-studio__tabs, .prompt-studio__actions, .prompt-studio__meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.prompt-studio__meta { justify-content: space-between; }
.prompt-studio__variables code { font-family: var(--font-mono, monospace); }
.prompt-studio__diff { border-top: 1px solid var(--color-border); padding-top: 8px; }
.prompt-studio__diff pre { max-height: 220px; overflow: auto; white-space: pre-wrap; font-size: var(--font-xs); }
</style>
