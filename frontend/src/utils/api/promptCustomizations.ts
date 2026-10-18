import axios from 'axios'

export const PROMPT_CUSTOMIZATION_MAX_CHARS = 500

export interface PromptCustomizations {
  chat: string
  feed: string
  media: string
  proactive: string
}

const EMPTY: PromptCustomizations = {
  chat: '', feed: '', media: '', proactive: '',
}

export async function getPromptCustomizations(): Promise<PromptCustomizations> {
  const { data } = await axios.get<PromptCustomizations>('/api/v1/prompt-customizations')
  return { ...EMPTY, ...data }
}

export async function putPromptCustomizations(
  values: PromptCustomizations,
): Promise<PromptCustomizations> {
  const { data } = await axios.put<PromptCustomizations>('/api/v1/prompt-customizations', values)
  return { ...EMPTY, ...data }
}

export async function getAdminPromptCustomizations(): Promise<PromptCustomizations> {
  const { data } = await axios.get<PromptCustomizations>('/api/v1/admin/prompt-customizations')
  return { ...EMPTY, ...data }
}

export async function putAdminPromptCustomizations(
  values: PromptCustomizations,
): Promise<PromptCustomizations> {
  const { data } = await axios.put<PromptCustomizations>('/api/v1/admin/prompt-customizations', values)
  return { ...EMPTY, ...data }
}
