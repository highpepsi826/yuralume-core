import axios from 'axios'
import type {
  CurrentIntentReconcileResponse,
  ProactiveAttempt,
  ProactiveEvaluateResponse,
} from '@/types/proactive'

const BASE = '/api/v1/characters'

export async function listProactiveAttempts(
  characterId: string,
  limit: number = 50,
): Promise<ProactiveAttempt[]> {
  const { data } = await axios.get<ProactiveAttempt[]>(
    `${BASE}/${characterId}/proactive/attempts`,
    { params: { limit } },
  )
  return data
}

export async function evaluateProactiveNow(
  characterId: string,
): Promise<ProactiveEvaluateResponse> {
  const { data } = await axios.post<ProactiveEvaluateResponse>(
    `${BASE}/${characterId}/proactive/evaluate`,
  )
  return data
}

export async function reconcileCurrentIntentNow(
  characterId: string,
): Promise<CurrentIntentReconcileResponse> {
  const { data } = await axios.post<CurrentIntentReconcileResponse>(
    `${BASE}/${characterId}/current-intent/reconcile`,
  )
  return data
}
