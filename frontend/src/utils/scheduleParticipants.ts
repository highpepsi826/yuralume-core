import type { ScheduleActivity } from '@/types/schedule'

/** Role the backend gives the operator's `participant_refs` entry once the
 * player has explicitly agreed to a shared activity
 * (`OPERATOR_CONFIRMED_SHARED_ROLE`). */
export const OPERATOR_CONFIRMED_SHARED_ROLE = 'operator_confirmed_shared'

/** True only for an activity the player has agreed to do together with the
 * character. Pending invites, one-sided wishes and lapsed/expired roles are
 * deliberately not shown as "together". */
export function isSharedWithOperator(
  activity: Pick<ScheduleActivity, 'participant_refs'>,
): boolean {
  return (activity.participant_refs ?? []).some(
    (ref) =>
      ref.actor_kind === 'operator' && ref.role === OPERATOR_CONFIRMED_SHARED_ROLE,
  )
}
