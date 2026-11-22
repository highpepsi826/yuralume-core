import { describe, expect, it } from 'vitest'
import { isSharedWithOperator } from '@/utils/scheduleParticipants'

const ref = (actor_kind: string, role: string | null) => ({
  actor_kind,
  actor_id: null,
  display_name: 'x',
  role,
})

describe('isSharedWithOperator', () => {
  it('is true for an operator ref with the confirmed-shared role', () => {
    expect(
      isSharedWithOperator({ participant_refs: [ref('operator', 'operator_confirmed_shared')] }),
    ).toBe(true)
  })

  it.each(['operator_invite_pending', 'operator_wish', 'operator_invite_expired', null])(
    'is false for operator role %s',
    (role) => {
      expect(isSharedWithOperator({ participant_refs: [ref('operator', role)] })).toBe(false)
    },
  )

  it('ignores the confirmed role on a non-operator ref and empty lists', () => {
    expect(
      isSharedWithOperator({ participant_refs: [ref('character', 'operator_confirmed_shared')] }),
    ).toBe(false)
    expect(isSharedWithOperator({ participant_refs: [] })).toBe(false)
  })
})
