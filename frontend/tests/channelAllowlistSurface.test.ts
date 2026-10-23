/**
 * (d1) 外部通道面板把「只留一個 sender」講明白，並把空清單的後果顯示出來。
 *
 * 這個面板的帳號卡片只有按開（`expandedAccountId`）才會渲染 allowlist
 * 區塊，而 repo 沒有 jsdom / @vue/test-utils，SSR 也模擬不了點擊，所以這裡
 * 用原始碼掃描釘住接線（與 `identityCardSettingsWiring.test.ts` 同一種作法）：
 * 警告掛在既有的 allowlist 區塊裡、用的是共用的純函式、文案走三語 catalog。
 * 判斷邏輯本身在 `allowlistWarning.test.ts` 用純函式測過。
 *
 * 設計檔要求的是「可見的警告」而不是「存檔被拒」：既有的空清單帳號不能被
 * 回溯停用，所以這個 diff 绝不能出現任何攔寫。
 */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { messages as zhTW } from '@/i18n/locales/zh-TW'
import { messages as enUS } from '@/i18n/locales/en-US'
import { messages as jaJP } from '@/i18n/locales/ja-JP'

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf-8')
    .replace(/\r\n/g, '\n')
}

const PANEL = source('../src/components/ChannelBindingsPanel.vue')
const CATALOGS = { 'zh-TW': zhTW, 'en-US': enUS, 'ja-JP': jaJP } as const

describe('allowlist 警告掛在既有的區塊裡', () => {
  it('用共用的 allowlistWarning 純函式，不在元件裡另寫一份判斷', () => {
    expect(PANEL).toContain(
      "import { allowlistWarning } from '@/utils/allowlistWarning'",
    )
    expect(PANEL).toContain('allowlistWarningFor(account)')
    // 舊的內聯版本（自己 filter/長度比較）必須不見，否則兩份規則會漂移。
    expect(PANEL).not.toContain('account.allowed_sender_refs.filter(')
  })

  it('兩個警告都在 allowlist 的 textarea 之後、bindings 區塊之前', () => {
    const labelAt = PANEL.indexOf("pt('channelBindingsPanel.allowlist.label')")
    const textareaAt = PANEL.indexOf('@change="handleSaveAllowlist', labelAt)
    const emptyAt = PANEL.indexOf("allowlistWarningFor(account) === 'empty'", textareaAt)
    const multipleAt = PANEL.indexOf(
      "allowlistWarningFor(account) === 'multiple'", textareaAt,
    )
    const bindingsAt = PANEL.indexOf("pt('channelBindingsPanel.bindings.title')", textareaAt)
    expect(labelAt).toBeGreaterThan(-1)
    expect(textareaAt).toBeGreaterThan(labelAt)
    expect(emptyAt).toBeGreaterThan(textareaAt)
    expect(multipleAt).toBeGreaterThan(emptyAt)
    expect(bindingsAt).toBeGreaterThan(multipleAt)
  })

  it('警告用琥珀色的 .channels-warning，不是跟錯誤混在一起的红框', () => {
    expect(PANEL).toContain('class="channels-warning"')
    expect(PANEL).toContain('.channels-warning {')
    // 這組設定存得下去，只是後果不如預期；用 .channels-error 會讓玩家以為
    // 存檔失敗了。
    const emptyBlockAt = PANEL.indexOf("allowlistWarningFor(account) === 'empty'")
    const blockEnd = PANEL.indexOf('</div>', emptyBlockAt)
    expect(PANEL.slice(emptyBlockAt, blockEnd)).toContain('channels-warning')
  })

  it('新建表單也講同一條規則（新建時就決定成不成立）', () => {
    const createAt = PANEL.indexOf("t('channelBindingsPanel.create.allowlist')")
    const hintAt = PANEL.indexOf(
      "t('channelBindingsPanel.allowlist.singleSenderHint')", createAt,
    )
    expect(hintAt).toBeGreaterThan(createAt)
  })
})

describe('不攔寫：空清單仍然送得出去', () => {
  it('handleSaveAllowlist 沒有新增任何空清單檢查', () => {
    const saveAt = PANEL.indexOf('async function handleSaveAllowlist')
    const saveBody = PANEL.slice(saveAt, PANEL.indexOf('async function handleDeleteAccount'))
    expect(saveBody).toContain('allowed_sender_refs: splitLines(raw)')
    expect(saveBody).not.toContain('if (!splitLines(raw).length)')
    expect(saveBody).not.toContain('return')
  })

  it('面板沒有動到後端的 persona 守門，也沒有任何停用帳號的呼叫', () => {
    // 註解裡提到函式名稱是可以的（說明這條規則是從哪來的）；真的去呼叫
    // 或重新實作它不行 —— 那是後端的判斷，設計檔明訂 read-only。
    expect(PANEL).not.toContain('persona_safe_for_account(')
    expect(PANEL).not.toContain('enabled: false')
  })
})

describe('文案三語齊備', () => {
  it('singleSenderHint / emptyWarning / multipleWarning 都存在且非空', () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      const allowlist = catalog.channelBindingsPanel.allowlist
      for (const key of ['singleSenderHint', 'emptyWarning', 'multipleWarning'] as const) {
        const value = allowlist[key]
        expect(typeof value, `${locale}.${key}`).toBe('string')
        expect(value.trim().length, `${locale}.${key}`).toBeGreaterThan(0)
      }
    }
  })

  it('警告說明的是「人設不會出現」，不只是「不限制」', () => {
    // 原本的 hint 只說「留空＝接受任何人」，玩家讀不出代價。新的警告必須
    // 點名被抑制的東西，否則等於沒說。
    expect(zhTW.channelBindingsPanel.allowlist.emptyWarning).toContain('人設')
    expect(enUS.channelBindingsPanel.allowlist.emptyWarning).toContain('persona')
    expect(jaJP.channelBindingsPanel.allowlist.emptyWarning).toContain('ペルソナ')
  })
})
