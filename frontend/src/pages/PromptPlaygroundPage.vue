<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { UiButton, UiSelect, UiTextarea } from '@/components/ui'
import { listPromptPlaygroundCharacters, runPromptPlayground, type PlaygroundResult, type PlaygroundCharacter } from '@/utils/api/promptPlayground'

const route = useRoute()
const adminScope = computed(() => route.query.scope === 'admin')
const characters = ref<PlaygroundCharacter[]>([])
const selectedId = ref('')
const message = ref('')
const includeProgress = ref(true)
const result = ref<PlaygroundResult | null>(null)
const loading = ref(true)
const running = ref(false)
const feedback = ref('')
const options = computed(() => characters.value.map((item) => ({ value: item.id, label: item.name })))
onMounted(async () => {
  try { characters.value = await listPromptPlaygroundCharacters(); selectedId.value = characters.value[0]?.id ?? '' }
  catch { feedback.value = '無法載入角色，請稍後再試。' }
  finally { loading.value = false }
})
async function run() {
  if (!selectedId.value || !message.value.trim()) return
  running.value = true; feedback.value = ''; result.value = null
  try { result.value = await runPromptPlayground(selectedId.value, { message: message.value, include_current_progress: includeProgress.value, draft_scope: adminScope.value ? 'admin' : 'player' }) }
  catch { feedback.value = '測試失敗，請檢查模型設定或稍後再試。' }
  finally { running.value = false }
}
function clear() { result.value = null; message.value = ''; feedback.value = '' }
</script>

<template>
  <main class="playground">
    <header><h1>Prompt Playground（提示詞測試場）</h1><p>以同一份唯讀快照比較目前有效版本與{{ adminScope ? '管理員' : '玩家' }} Draft，不保存測試對話或記憶。</p><RouterLink :to="adminScope ? '/admin/prompt-settings' : '/'">{{ adminScope ? '回到 Prompt Studio' : '返回遊玩頁／個人設定' }}</RouterLink></header>
    <p>測試會使用目前聊天模型，可能消耗 provider 額度。雙版本比較會呼叫模型兩次，輸出仍可能受模型隨機性影響。只有已儲存的 Draft 會參與比較。</p>
    <p>首版只測聊天文字回覆；貼文、短影片與主動訊息模板的 Draft 不會反映在聊天結果。</p>
    <section class="controls">
      <UiSelect v-model="selectedId" :options="options" label="角色" :disabled="loading || running" @update:model-value="result = null" />
      <label><input v-model="includeProgress" type="checkbox" :disabled="running">帶入目前遊玩進度</label>
      <UiTextarea v-model="message" label="測試訊息" :rows="4" :maxlength="2000" :disabled="running" />
      <div class="actions"><UiButton :loading="running" :disabled="loading || running || !selectedId || !message.trim()" @click="run">執行測試</UiButton><UiButton variant="ghost" :disabled="running" @click="clear">清除本頁結果</UiButton></div>
      <p v-if="!loading && !characters.length">尚無可測試的角色。</p>
    </section>
    <p v-if="feedback" role="alert">{{ feedback }}</p>
    <section v-if="result" class="results">
      <article><h2>目前有效版本</h2><p>{{ result.published_reply }}</p><small>Prompt hash：{{ result.prompt_hash }}</small></article>
      <article><h2>Draft 版本</h2><p>{{ result.draft_reply ?? '尚無 Draft 可比較。請先在 Prompt Studio 儲存 Draft。' }}</p><small v-if="result.draft_prompt_hash">Prompt hash：{{ result.draft_prompt_hash }}</small></article>
    </section>
    <p v-if="result">模型：{{ result.model_id || '供應商預設' }}；Prompt hash：{{ result.prompt_hash }}。快照：正式對話 {{ result.snapshot_summary.recent_message_count }} 則、記憶 {{ result.snapshot_summary.memory_count }} 項、目前活動 {{ result.snapshot_summary.has_current_activity ? '有' : '無' }}、故事弧 {{ result.snapshot_summary.has_story_arc ? '有' : '無' }}。結果離開頁面即清除。</p>
  </main>
</template>

<style scoped>
.playground { max-width: 1100px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 18px; }
.playground h1, .playground h2 { margin: 0; }
.playground p { line-height: 1.65; }
.controls { display: flex; flex-direction: column; gap: 14px; }
.actions { display: flex; gap: 12px; }
.results { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.results article { border: 1px solid var(--color-border); padding: 16px; min-height: 180px; }
.results p { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 720px) { .playground { padding: 16px; } .results { grid-template-columns: 1fr; } }
</style>
