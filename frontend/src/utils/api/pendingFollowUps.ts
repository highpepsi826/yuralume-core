import axios from 'axios'

export interface PendingFollowUpMessage {
  content: string
  queued_at: string
}

export interface PendingFollowUp {
  id: string
  character_id: string
  conversation_id: string
  status: 'queued' | 'resolving' | 'resolved' | 'cancelled'
  brief_reply: string
  defer_reason: string
  scheduled_for: string
  queued_at: string
  updated_at: string
  resolved_at: string | null
  last_error: string | null
  messages: PendingFollowUpMessage[]
}

export interface AdminPendingFollowUp extends PendingFollowUp {
  kind: 'busy_defer' | 'scheduled_promise' | string
  promise_intent: string
  commitment_key: string | null
}

export interface CreateScheduledPromiseInput {
  character_id: string
  conversation_id?: string | null
  scheduled_for: string
  promise_intent: string
}

export interface UpdateScheduledPromiseInput {
  scheduled_for?: string
  promise_intent?: string
}

export interface PendingFollowUpTickResult {
  resolved: number
}

const BASE = '/api/v1'

export async function listOpenPendingFollowUps(
  characterId: string,
): Promise<PendingFollowUp[]> {
  const { data } = await axios.get<PendingFollowUp[]>(
    `${BASE}/characters/${characterId}/pending-follow-ups`,
  )
  return data
}

export async function listDuePendingFollowUps(): Promise<PendingFollowUp[]> {
  const { data } = await axios.get<PendingFollowUp[]>(
    `${BASE}/admin/pending-follow-ups`,
  )
  return data
}

export async function listAdminPendingFollowUps(
  characterId: string,
): Promise<AdminPendingFollowUp[]> {
  const { data } = await axios.get<AdminPendingFollowUp[]>(
    `${BASE}/admin/pending-follow-ups/characters/${characterId}`,
  )
  return data
}

export async function createScheduledPromise(
  input: CreateScheduledPromiseInput,
): Promise<AdminPendingFollowUp> {
  const { data } = await axios.post<AdminPendingFollowUp>(
    `${BASE}/admin/pending-follow-ups`,
    input,
  )
  return data
}

export async function updateScheduledPromise(
  followUpId: string,
  input: UpdateScheduledPromiseInput,
): Promise<AdminPendingFollowUp> {
  const { data } = await axios.patch<AdminPendingFollowUp>(
    `${BASE}/admin/pending-follow-ups/${followUpId}`,
    input,
  )
  return data
}

export async function deleteScheduledPromise(followUpId: string): Promise<void> {
  await axios.delete(`${BASE}/admin/pending-follow-ups/${followUpId}`)
}

export async function triggerPendingFollowUpTick(): Promise<PendingFollowUpTickResult> {
  const { data } = await axios.post<PendingFollowUpTickResult>(
    `${BASE}/admin/pending-follow-ups/tick`,
  )
  return data
}
