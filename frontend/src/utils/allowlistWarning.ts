/**
 * 「允許的 sender_ref」清單在畫面上該不該喊警告。
 *
 * 後端 `persona_disclosure_gate.persona_safe_for_account` 只在清單剛好一個
 * sender 時放行：空清單雖然代表「誰都能跟角色說話」，但同一個空值也讓人設
 * （OperatorPersona）、玩家自述（player_persona_note）與解析後的稱呼整段
 * 不進提示詞，而且沒有任何錯誤訊息。這裡只負責把那個後果講出來——判斷邏輯
 * 跟後端一致，不 trim、只略過空字串，否則畫面會跟實際行為對不上。
 *
 * 寫入路徑上的 `splitLines` 會 trim 掉每一行，所以正常存進去的值不會帶
 * 前後空白；這個函式因此不必自己再清一次。
 */
export type AllowlistWarning = 'empty' | 'multiple' | null

export function allowlistWarning(
  allowedSenderRefs: readonly string[] | null | undefined,
): AllowlistWarning {
  const senders = (allowedSenderRefs ?? []).filter(ref => ref.length > 0)
  if (senders.length === 0) return 'empty'
  if (senders.length > 1) return 'multiple'
  return null
}
