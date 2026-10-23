/**
 * (d1) 外部通道 allowlist 的警告判斷。
 *
 * 這條規則的存在理由：後端 `persona_safe_for_account` 只在清單剛好一個
 * sender 時放行，空清單會讓人設、玩家自述與解析後的稱呼整段不進提示詞，
 * 而且沒有任何錯誤。UI 不改那個判斷（設計檔明訂 read-only），只把後果講
 * 出來，所以「什麼時候該喊」必須跟後端一字不差。
 *
 * 這裡只測純函式；面板上警告是否真的渲染、文案是不是三語都有，在
 * `channelAllowlistSurface.test.ts`。
 */

import { describe, expect, it } from 'vitest'

import { allowlistWarning } from '@/utils/allowlistWarning'

describe('allowlistWarning', () => {
  it('空清單 → empty（後端此時不揭露人設）', () => {
    expect(allowlistWarning([])).toBe('empty')
    expect(allowlistWarning(null)).toBe('empty')
    expect(allowlistWarning(undefined)).toBe('empty')
  })

  it('剛好一個 sender → 不警告，這是後端唯一放行的形狀', () => {
    expect(allowlistWarning(['user-1'])).toBeNull()
  })

  it('多個 sender → multiple（群組／共用帳號同樣不揭露）', () => {
    expect(allowlistWarning(['user-1', 'user-2'])).toBe('multiple')
  })

  it('純空字串不算 sender', () => {
    expect(allowlistWarning([''])).toBe('empty')
    expect(allowlistWarning(['', '', ''])).toBe('empty')
    expect(allowlistWarning(['', 'user-1'])).toBeNull()
    expect(allowlistWarning(['user-1', ''])).toBeNull()
    expect(allowlistWarning(['user-1', 'user-2', ''])).toBe('multiple')
  })

  it('與後端一致：不 trim，所以純空白仍算一個 sender', () => {
    // 後端過濾條件是 `if ref`，寫入路徑的 splitLines 已經 trim 過每一行，
    // 正常資料不會走到這裡。若這裡自己 trim，畫面就會在後端其實放行時
    // 喊警告 —— 兩個實作必須同形狀。
    expect(allowlistWarning(['  '])).toBeNull()
    expect(allowlistWarning([' ', ' user-1 '])).toBe('multiple')
  })
})
