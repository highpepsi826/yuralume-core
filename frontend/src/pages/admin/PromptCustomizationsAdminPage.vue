<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { UiBadge, UiButton, UiSection } from '@/components/ui'
import {
  getAdminPromptCustomizations,
  putAdminPromptCustomizations,
  PROMPT_CUSTOMIZATION_MAX_CHARS,
  type PromptCustomizations,
} from '@/utils/api/promptCustomizations'

const values = reactive<PromptCustomizations>({ chat: '', feed: '', media: '', proactive: '' })
const loading = ref(true)
const saving = ref(false)
const feedback = ref('')
const fields: Array<[keyof PromptCustomizations, string]> = [
  ['chat', '聊天回覆'], ['feed', 'LumeGram 文案'], ['media', '圖片與短影片風格'], ['proactive', '主動訊息語氣'],
]

async function load() {
  loading.value = true
  try { Object.assign(values, await getAdminPromptCustomizations()) }
  catch (error) { feedback.value = error instanceof Error ? error.message : '無法讀取設定。' }
  finally { loading.value = false }
}
async function save() {
  saving.value = true; feedback.value = ''
  try { Object.assign(values, await putAdminPromptCustomizations({ ...values })); feedback.value = '已儲存。' }
  catch (error) { feedback.value = error instanceof Error ? error.message : '儲存失敗。' }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <div class="prompt-admin">
    <header><div><h1>Prompt 設定</h1><p>為所有使用者與角色加入受控的表現偏好。</p></div><UiBadge variant="primary">Admin</UiBadge></header>
    <UiSection title="重要提示" bordered>
      <p class="prompt-admin__warning">這些內容影響所有使用者與角色。它們只能補充表現口味，不能取代角色設定、事實、工具、輸出格式或核心規則。</p>
      <p v-if="loading">載入中…</p>
      <template v-else>
        <label v-for="[key, label] in fields" :key="key" class="field-label">{{ label }}<textarea v-model="values[key]" class="field-input" rows="4" :maxlength="PROMPT_CUSTOMIZATION_MAX_CHARS" /></label>
        <UiButton variant="primary" :loading="saving" @click="save">儲存重要提示</UiButton>
      </template>
      <p v-if="feedback" class="prompt-admin__feedback">{{ feedback }}</p>
    </UiSection>
  </div>
</template>

<style scoped>
.prompt-admin { display: flex; flex-direction: column; gap: 16px; }.prompt-admin header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }.prompt-admin h1, .prompt-admin p { margin: 0; }.prompt-admin header p, .prompt-admin__feedback { color: var(--color-text-secondary); margin-top: 4px; }.prompt-admin__warning { margin-bottom: 12px !important; color: #e9bb72; line-height: 1.55; }.field-label { display: flex; flex-direction: column; gap: 5px; margin: 12px 0; }.field-input { resize: vertical; }
</style>
