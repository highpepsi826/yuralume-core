<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { UiButton } from '@/components/ui'
import {
  getPromptCustomizations,
  putPromptCustomizations,
  PROMPT_CUSTOMIZATION_MAX_CHARS,
  type PromptCustomizations,
} from '@/utils/api/promptCustomizations'

const values = reactive<PromptCustomizations>({ chat: '', feed: '', media: '', proactive: '' })
const loading = ref(true)
const saving = ref(false)
const feedback = ref('')

async function load() {
  loading.value = true
  try {
    Object.assign(values, await getPromptCustomizations())
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '無法讀取設定。'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  feedback.value = ''
  try {
    Object.assign(values, await putPromptCustomizations({ ...values }))
    feedback.value = '已儲存。新的生成會套用這些偏好。'
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '儲存失敗。'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="prompt-customization">
    <p class="prompt-customization__hint">
      這是表現口味，不會覆寫角色設定、事實、工具規則或安全規則。留空即不額外影響該類生成。
    </p>
    <p v-if="loading" class="prompt-customization__hint">載入中…</p>
    <template v-else>
      <label v-for="[key, label] in [['chat', '聊天回覆'], ['feed', 'LumeGram 文案'], ['media', '圖片與短影片風格'], ['proactive', '主動訊息語氣']]" :key="key" class="field-label">
        {{ label }}
        <textarea v-model="values[key as keyof PromptCustomizations]" class="field-input" rows="3" :maxlength="PROMPT_CUSTOMIZATION_MAX_CHARS" />
      </label>
      <UiButton variant="primary" size="sm" :loading="saving" @click="save">儲存偏好</UiButton>
    </template>
    <p v-if="feedback" class="prompt-customization__feedback">{{ feedback }}</p>
  </div>
</template>

<style scoped>
.prompt-customization { display: flex; flex-direction: column; gap: 10px; }
.prompt-customization__hint, .prompt-customization__feedback { margin: 0; color: var(--color-text-secondary); font-size: var(--font-xs); line-height: 1.55; }
.field-input { resize: vertical; }
</style>
