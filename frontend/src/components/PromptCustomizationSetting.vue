<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { UiBadge, UiButton, UiTextarea } from '@/components/ui'
import {
  getPlayerPromptTemplate,
  listPlayerPromptTemplates,
  putPlayerPromptTemplate,
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

async function selectTemplate(name: string) {
  feedback.value = ''
  try {
    selected.value = await getPlayerPromptTemplate(name)
    draft.value = selected.value.content
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取 prompt。'
  }
}

async function load() {
  loading.value = true
  try {
    templates.value = await listPlayerPromptTemplates()
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
    selected.value = await putPlayerPromptTemplate(selected.value.name, content)
    draft.value = selected.value.content
    templates.value = await listPlayerPromptTemplates()
    feedback.value = content.trim() ? '已儲存覆寫，新生成會使用這份模板。' : '已還原目前的預設模板。'
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '儲存失敗。'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="prompt-studio">
    <p class="prompt-studio__hint">
      你可直接覆寫可見功能的 prompt。角色資料、記憶、時間、行程與對話內容仍會在每次生成時動態注入；請保留下方列出的 <code>$變數</code>。
    </p>
    <p v-if="loading" class="prompt-studio__hint">載入中…</p>
    <template v-else>
      <div class="prompt-studio__tabs" role="tablist" aria-label="可自訂 prompt">
        <UiButton
          v-for="template in templates"
          :key="template.name"
          size="sm"
          :variant="template.name === selectedName ? 'primary' : 'secondary'"
          :active="template.name === selectedName"
          @click="selectTemplate(template.name)"
        >{{ template.title }}</UiButton>
      </div>
      <template v-if="selected">
        <div class="prompt-studio__meta">
          <strong>{{ selected.title }}</strong>
          <UiBadge :variant="selected.overridden ? 'primary' : 'default'">
            {{ selected.overridden ? '已覆寫' : '目前預設' }}
          </UiBadge>
        </div>
        <p class="prompt-studio__impact">{{ selected.impact }}</p>
        <p class="prompt-studio__variables">
          必須保留的變數：{{ selected.variables.length ? selected.variables.map((name) => `$${name}`).join('、') : '無' }}
        </p>
        <UiTextarea v-model="draft" :rows="14" :maxlength="24000" label="Prompt 模板" />
        <div class="prompt-studio__actions">
          <UiButton variant="primary" size="sm" :loading="saving" @click="save()">儲存覆寫</UiButton>
          <UiButton variant="ghost" size="sm" :disabled="saving || !selected.overridden" @click="save('')">還原目前預設</UiButton>
        </div>
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
</style>
