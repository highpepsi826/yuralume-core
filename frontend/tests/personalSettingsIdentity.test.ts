/**
 * 個人設定頁的兩件事：(a) 提示詞工作室挪到「全域體驗偏好」的最後，
 * (b) 新增代名詞欄位，寫入既有的 `OperatorProfile.pronouns`。
 *
 * 這個 repo 沒有 jsdom / @vue/test-utils（見 `identityCardWizard.test.ts`
 * 檔頭），所以元件層用 SSR 真的渲染一次 —— 順序與欄位存在與否都是渲染
 * 結果，不是原始碼字串比對；「存檔送什麼 payload」則用原始碼釘住呼叫點，
 * 因為 SSR 不執行事件處理器。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'

import { messages as zhTW } from '@/i18n/locales/zh-TW'
import { messages as enUS } from '@/i18n/locales/en-US'
import { messages as jaJP } from '@/i18n/locales/ja-JP'

// 每一個子設定都打自己的 API；測試只關心這一個父層的版面與接線，所以
// 除了代名詞欄位實際讀到的 profile 之外，其餘一律換成有名字的標記。
vi.mock('@/composables/useAuth', () => ({
  useAuth: () => ({
    authEnabled: true,
    currentUser: ref({ id: 'user-1' }),
    isAdmin: false,
    cloudMode: ref(false),
    logout: vi.fn(),
  }),
}))

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRouter: () => ({ replace: vi.fn() }),
}))

vi.mock('@/utils/authedFetch', () => ({ authedFetch: vi.fn() }))

vi.mock('@/utils/api/operatorProfile', () => ({
  getOperatorProfile: vi.fn(),
  updateOperatorProfile: vi.fn(),
}))

const marker = (id: string) => ({
  default: defineComponent({ setup: () => () => h('div', { id }, id) }),
})
vi.mock('@/components/ChatAssistSetting.vue', () => marker('MARKER_CHAT_ASSIST'))
vi.mock('@/components/PromptCustomizationSetting.vue', () => marker('MARKER_PLAYGROUND'))
vi.mock('@/components/TtsPregenSetting.vue', () => marker('MARKER_TTS'))
vi.mock('@/components/WebNotificationSetting.vue', () => marker('MARKER_WEB_NOTIFY'))
vi.mock('@/components/VisualGenerationStyleSetting.vue', () => marker('MARKER_VISUAL'))
vi.mock('@/components/NsfwModeSetting.vue', () => marker('MARKER_NSFW'))
vi.mock('@/components/QuotaOverageSettings.vue', () => marker('MARKER_OVERAGE'))
vi.mock('@/components/PlayerPlaceLocaleSettings.vue', () => marker('MARKER_PLACE'))
vi.mock('@/components/IdentityCardManagerPanel.vue', () => marker('MARKER_IDENTITY_CARDS'))
vi.mock('@/components/PlayerPasswordPanel.vue', () => marker('MARKER_PASSWORD'))

const { getOperatorProfile } = await import('@/utils/api/operatorProfile')
const { default: PersonalSettingsSection }
  = await import('@/components/PersonalSettingsSection.vue')
const personalSettingsSource = (
  await import('@/components/PersonalSettingsSection.vue?raw')
).default as string

const CATALOGS = {
  'zh-TW': zhTW,
  'en-US': enUS,
  'ja-JP': jaJP,
} as const

/**
 * `?raw` 取回的是檔案原文。工作區若是 CRLF checkout，每一段以 `\n` 寫成的
 * 多行比對都會落空，而失敗訊息會說「接線不見了」，其實是換行符號不同。
 * 與 `identityCardSettingsWiring.test.ts` 同一種處理。
 */
function source(): string {
  return personalSettingsSource.replace(/\r\n/g, '\n')
}

function profile(overrides: Record<string, unknown> = {}) {
  return {
    id: 'user-1',
    display_name: '桃桃',
    aliases: [],
    pronouns: null,
    timezone_id: 'Asia/Taipei',
    has_real_name: true,
    display_name_locked: true,
    country_code: null,
    latitude: null,
    longitude: null,
    location_label: null,
    ...overrides,
  }
}

async function render(locale: keyof typeof CATALOGS = 'zh-TW'): Promise<string> {
  const app = createSSRApp(PersonalSettingsSection)
  app.use(createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'zh-TW',
    messages: CATALOGS,
  }))
  return renderToString(app)
}

beforeEach(() => {
  vi.mocked(getOperatorProfile).mockReset()
  vi.mocked(getOperatorProfile).mockResolvedValue(profile() as never)
})

describe('(a) 提示詞工作室排在「全域體驗偏好」的最後', () => {
  it('偏好項目先出現，工作室在群組最後', async () => {
    const html = await render()
    const groupAt = html.indexOf('settings-group')
    expect(groupAt).toBeGreaterThan(-1)
    const order = [
      'MARKER_CHAT_ASSIST',
      'MARKER_TTS',
      'MARKER_WEB_NOTIFY',
      'MARKER_VISUAL',
      'MARKER_NSFW',
      'MARKER_OVERAGE',
      'MARKER_PLAYGROUND',
    ].map(id => html.indexOf(id, groupAt))

    for (const position of order) expect(position).toBeGreaterThan(groupAt)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
  })

  it('工作室仍然在同一個群組裡、仍然可以到達（不是被刪掉或搬出群組）', async () => {
    const html = await render()
    const groupStart = html.indexOf('settings-group')
    const groupEnd = html.lastIndexOf('</section>')
    const playgroundAt = html.indexOf('MARKER_PLAYGROUND')
    expect(playgroundAt).toBeGreaterThan(groupStart)
    expect(playgroundAt).toBeLessThan(groupEnd)
    // 挪動只動位置，不動元件本身：沒有任何 props 或條件把它藏起來。
    expect(source()).toContain('<PromptCustomizationSetting />')
  })
})

describe('(b) 代名詞欄位', () => {
  it('渲染在身份區塊裡，label / 儲存鍵 / 既有值是三種語系都有的文案', async () => {
    for (const locale of Object.keys(CATALOGS) as Array<keyof typeof CATALOGS>) {
      const html = await render(locale)
      expect(html).toContain('id="operator-pronouns"')
      expect(html).toContain(
        CATALOGS[locale].playerSidebar.pronouns.label,
      )
      expect(html).toContain(
        CATALOGS[locale].playerSidebar.pronouns.save,
      )
    }
  })

  it('身份區塊裡的代名詞緊接在顯示名稱之後', async () => {
    const html = await render()
    const nameAt = html.indexOf('id="operator-display-name"')
    const pronounAt = html.indexOf('id="operator-pronouns"')
    const placeAt = html.indexOf('MARKER_PLACE')
    expect(nameAt).toBeGreaterThan(-1)
    expect(pronounAt).toBeGreaterThan(nameAt)
    expect(placeAt).toBeGreaterThan(pronounAt)
  })

  it('已存的代名詞會回填到輸入框', async () => {
    // SSR 不會等 `watch(..., { immediate: true })` 的 profile GET 解析完
    // （onMounted 在 SSR 根本不會跑），所以「回填」只能釘在共用的
    // `applyOperatorProfile` 上 —— 它同時餵顯示名稱與代名詞，一次 GET
    // 兩個欄位就不會各走各的。
    expect(source()).toContain(
      'pronounDraft.value = profile.pronouns ?? \'\'',
    )
    const applyAt = source().indexOf('function applyOperatorProfile')
    const seedAt = source().indexOf(
      'pronounDraft.value = profile.pronouns', applyAt,
    )
    // 正在儲存時不要被一個較慢的 GET 蓋掉玩家剛打的字。
    expect(seedAt).toBeGreaterThan(applyAt)
    expect(source()).toContain('if (!pronounSaving.value) {')
  })

  it('上限 64 對齊後端 `pronouns` 欄位的 String(64)', async () => {
    expect(source()).toContain('maxlength="64"')
  })

  it('存檔走既有的 updateOperatorProfile，只送 pronouns', async () => {
    expect(source()).toContain(
      "import {\n  getOperatorProfile,\n  updateOperatorProfile,\n} from '@/utils/api/operatorProfile'",
    )
    const saveAt = source().indexOf('async function savePronouns')
    const callAt = source().indexOf(
      'updateOperatorProfile({\n      pronouns: pronounDraft.value.trim(),\n    })',
      saveAt,
    )
    // 必須是空字串而不是 null：null 在後端代表「不要動這個欄位」，
    // 送 null 會讓清空代名詞變成 no-op。entity 的 __post_init__ 把空字串
    // trim 成 None，所以清空仍然寫入 NULL。
    expect(callAt).toBeGreaterThan(saveAt)
    expect(source()).not.toContain('pronouns: pronounDraft.value.trim() || null')
  })

  it('存檔後把回傳的 profile 套回去並通知其他頁面', async () => {
    const saveAt = source().indexOf('async function savePronouns')
    const applyAt = source().indexOf(
      'applyOperatorProfile(profile)', saveAt,
    )
    const dispatchAt = source().indexOf(
      "'kokoro:operator-profile-updated'", saveAt,
    )
    expect(applyAt).toBeGreaterThan(saveAt)
    expect(dispatchAt).toBeGreaterThan(applyAt)
  })
})

describe('(b) 代名詞只和已存的名稱一起進提示詞', () => {
  // `_render_operator_block` 在沒有已存名稱時整段回傳 []，所以「只有代名詞
  // 沒有名稱」等於代名詞進不了任何提示。那個行為由
  // `tests/unit/test_prompt_address_integration.py` 釘住；這裡釘 UI 那一半：
  // 玩家要在沒有名稱時看到一句解釋。
  it('提示的顯示條件綁的是已存名稱（has_real_name），不是編輯中的草稿', () => {
    expect(source()).toContain(
      'v-if="operatorProfile && !operatorProfile.has_real_name"',
    )
    // 用草稿判斷會在每次 opened、profile 還沒回來時先閃一次警告。
    expect(source()).not.toContain('!displayNameDraft.trim()" class="display-name-hint"')
  })

  it('三種語系都有這句提示，且不是空字串', () => {
    for (const catalog of Object.values(CATALOGS)) {
      const hint = catalog.playerSidebar.pronouns.needsDisplayNameHint
      expect(typeof hint).toBe('string')
      expect(hint.trim().length).toBeGreaterThan(0)
    }
  })

  it('代名詞欄位在 profile 載入完成前是停用的，避免覆寫成空白', () => {
    expect(source()).toContain(':disabled="pronounSaving || profileLoading"')
  })
})
