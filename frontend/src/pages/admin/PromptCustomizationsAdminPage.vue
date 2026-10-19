<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { UiBadge, UiButton, UiSection, UiTextarea } from '@/components/ui'
import {
  getAdminPromptTemplate,
  listAdminPromptTemplates,
  putAdminPromptTemplate,
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

async function selectTemplate(name: string) {
  feedback.value = ''
  try {
    selected.value = await getAdminPromptTemplate(name)
    draft.value = selected.value.content
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取 prompt。'
  }
}

async function load() {
  loading.value = true
  try {
    templates.value = await listAdminPromptTemplates()
    if (templates.value[0]) await selectTemplate(templates.value[0].name)
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取設定。'
  } finally {
    loading.value = false
  }
}

async function save(content = draft.value) {
  if (!selected.value) return
  saving.value = true
  feedback.value = ''
  try {
    selected.value = await putAdminPromptTemplate(selected.value.name, content)
    draft.value = selected.value.content
    templates.value = await listAdminPromptTemplates()
    feedback.value = content.trim() ? '已儲存全站覆寫。' : '已還原內建預設。'
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '儲存失敗。'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="prompt-admin">
    <header>
      <div><h1>Prompt Studio</h1><p>管理所有已登錄的 prompt 模板與全站預設。儲存後其他服務會在約 10 秒內套用。</p></div>
      <UiBadge variant="primary">Admin</UiBadge>
    </header>
    <p v-if="loading" class="prompt-admin__hint">載入中…</p>
    <template v-else>
      <UiSection v-if="selected" :title="selected.title" bordered>
        <div class="prompt-admin__meta">
          <UiBadge :variant="selected.overridden ? 'primary' : 'default'">{{ selected.overridden ? '已覆寫' : '內建預設' }}</UiBadge>
          <UiBadge v-if="selected.important" variant="danger">重要 prompt</UiBadge>
        </div>
        <p :class="selected.important ? 'prompt-admin__warning' : 'prompt-admin__hint'">
          {{ selected.important ? `重要 prompt，改了會影響：${selected.impact}` : selected.impact }}
        </p>
        <p class="prompt-admin__hint">必須保留的變數：{{ selected.variables.length ? selected.variables.map((name) => `$${name}`).join('、') : '無' }}</p>
        <UiTextarea v-model="draft" :rows="18" :maxlength="24000" label="Prompt 模板" />
        <div class="prompt-admin__actions">
          <UiButton variant="primary" :loading="saving" @click="save()">儲存全站覆寫</UiButton>
          <UiButton variant="ghost" :disabled="saving || !selected.overridden" @click="save('')">還原內建預設</UiButton>
        </div>
      </UiSection>
      <UiSection v-for="category in categories" :key="category" :title="category" bordered>
        <div class="prompt-admin__templates">
          <UiButton
            v-for="template in templates.filter((item) => item.category === category)"
            :key="template.name"
            size="sm"
            :variant="template.name === selectedName ? 'primary' : 'secondary'"
            :active="template.name === selectedName"
            @click="selectTemplate(template.name)"
          >{{ template.title }}</UiButton>
        </div>
      </UiSection>
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
</style>
