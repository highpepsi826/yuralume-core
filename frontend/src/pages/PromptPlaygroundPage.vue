<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAuth } from '@/composables/useAuth'
import { UiButton, UiSelect, UiTextarea } from '@/components/ui'
import { listPromptPlaygroundCharacters, runPromptPlayground, previewPromptPlayground, type PlaygroundPreview, type PlaygroundResult, type PlaygroundCharacter } from '@/utils/api/promptPlayground'

const route = useRoute()
const { isAdmin } = useAuth()
const scope = ref<'player' | 'admin'>(route.query.scope === 'admin' ? 'admin' : 'player')
const adminScope = computed(() => scope.value === 'admin')
watch(() => route.query.scope, value => { scope.value = value === 'admin' ? 'admin' : 'player' })
const preview = ref<PlaygroundPreview | null>(null)
const previewLoading = ref(false)
const previewError = ref('')
let previewRequest = 0
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
async function refreshPreview() {
  const request = ++previewRequest
  preview.value = null; previewError.value = ''
  if (!selectedId.value) { previewLoading.value = false; return }
  previewLoading.value = true
  try {
    const data = await previewPromptPlayground(selectedId.value, { include_current_progress: includeProgress.value, draft_scope: scope.value })
    if (request === previewRequest) preview.value = data
  } catch { if (request === previewRequest) previewError.value = '無法預覽已儲存 Draft，請重新載入。' }
  finally { if (request === previewRequest) previewLoading.value = false }
}
watch([selectedId, includeProgress, scope], () => { result.value = null; void refreshPreview() })
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
      <UiSelect v-if="isAdmin" v-model="scope" :options="[{ value: 'player', label: '我的玩家 Draft（個人口味）' }, { value: 'admin', label: '我的管理員 Draft（全站模板）' }]" label="測試 Draft 範圍" :disabled="running" />
      <UiSelect v-model="selectedId" :options="options" label="角色" :disabled="loading || running" @update:model-value="result = null" />
      <label><input v-model="includeProgress" type="checkbox" :disabled="running">帶入目前遊玩進度</label>
      <section aria-label="測試 Draft 清單">
        <h2>本次測試的已儲存 Draft</h2>
        <p>使用{{ adminScope ? '你自己的管理員' : '你自己的玩家' }} Draft；不會使用其他人的草稿。執行時會重新讀取並凍結版本，以結果清單為準。</p>
        <UiButton variant="ghost" :disabled="running || previewLoading || !selectedId" @click="refreshPreview">重新載入 Draft 清單</UiButton>
        <p v-if="previewLoading">正在預覽…</p>
        <p v-if="previewError" role="alert">{{ previewError }}</p>
        <template v-if="preview">
          <p>已儲存 {{ preview.draft_templates.length }} 份；預計用於本次聊天 {{ preview.draft_templates.filter(item => item.used).length }} 份。</p>
          <ul><li v-for="item in preview.draft_templates" :key="item.name">{{ item.title }} — {{ item.used ? '會用於本次聊天' : '未使用：不在本次聊天組裝路徑／條件未滿足' }}（{{ item.content_hash }}）</li></ul>
          <p v-if="!preview.draft_templates.length">尚未儲存 Draft，本次只產生目前有效版本。</p>
        </template>
      </section>
      <UiTextarea v-model="message" label="測試訊息" :rows="4" :maxlength="2000" :disabled="running" />
      <div class="actions"><UiButton :loading="running" :disabled="loading || running || !selectedId || !message.trim()" @click="run">執行測試</UiButton><UiButton variant="ghost" :disabled="running" @click="clear">清除本頁結果</UiButton></div>
      <p v-if="!loading && !characters.length">尚無可測試的角色。</p>
    </section>
    <p v-if="feedback" role="alert">{{ feedback }}</p>
    <section v-if="result" class="results">
      <article><h2>目前有效版本</h2><p>{{ result.published_reply }}</p><small>Prompt hash：{{ result.prompt_hash }}</small></article>
      <article><h2>Draft 版本</h2><p>{{ result.draft_reply ?? '尚無 Draft 可比較。請先在 Prompt Studio 儲存 Draft。' }}</p><small v-if="result.draft_prompt_hash">Prompt hash：{{ result.draft_prompt_hash }}</small></article>
    </section>
    <section v-if="result" aria-label="本次實際使用的模板">
      <h2>本次實際組入提示詞的模板</h2>
      <p>下列模板內容已組入送給模型的提示詞；這不代表模型一定遵從了每段指示。角色卡、記憶等動態資料另外注入。</p>
      <div class="results">
        <article v-for="version in (['published', 'draft'] as const)" :key="version">
          <h3>{{ version === 'published' ? '目前有效版本' : 'Draft 版本' }}</h3>
          <ul><li v-for="item in result.template_usage[version]" :key="item.name">{{ item.title }} — {{ item.source === 'draft' ? '已套用 Draft' : '目前有效版本' }}（{{ item.content_hash }}）</li></ul>
          <p v-if="version === 'draft' && !result.has_draft">沒有 Draft，未執行第二次生成。</p>
        </article>
      </div>
      <h3>本次 Draft 使用狀態</h3>
      <ul><li v-for="item in result.draft_templates" :key="item.name">{{ item.title }} — {{ item.used ? '已用於 Draft 結果' : '未使用：不在本次聊天組裝路徑／條件未滿足' }}（{{ item.content_hash }}）</li></ul>
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
