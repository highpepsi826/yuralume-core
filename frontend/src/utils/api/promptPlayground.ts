import axios from 'axios'

export interface PlaygroundCharacter { id: string; name: string }
export interface TemplateUsage { name: string; title: string; source: 'effective' | 'draft'; content_hash: string }
export interface DraftTemplate { name: string; title: string; used: boolean; content_hash: string }
export interface PlaygroundPreview {
  template_usage: { published: TemplateUsage[]; draft: TemplateUsage[] }
  draft_templates: DraftTemplate[]
}
export interface PlaygroundResult extends PlaygroundPreview {
  published_reply: string
  draft_reply: string | null
  model_id: string | null
  prompt_hash: string
  draft_prompt_hash: string | null
  provider_id: string
  elapsed_ms: number
  has_draft: boolean
  snapshot_summary: Record<string, number | boolean>
}
export async function listPromptPlaygroundCharacters(): Promise<PlaygroundCharacter[]> {
  const { data } = await axios.get<{ characters: PlaygroundCharacter[] }>('/api/v1/prompt-playground/characters')
  return data.characters
}
export async function runPromptPlayground(characterId: string, payload: { message: string; include_current_progress: boolean; draft_scope: 'player' | 'admin' }): Promise<PlaygroundResult> {
  const { data } = await axios.post<PlaygroundResult>(`/api/v1/characters/${encodeURIComponent(characterId)}/prompt-playground/runs`, payload)
  return data
}

export async function previewPromptPlayground(characterId: string, params: { include_current_progress: boolean; draft_scope: 'player' | 'admin' }): Promise<PlaygroundPreview> {
  const { data } = await axios.get<PlaygroundPreview>(`/api/v1/characters/${encodeURIComponent(characterId)}/prompt-playground/preview`, { params })
  return data
}
