import axios from 'axios'

export interface PromptTemplateSummary {
  name: string
  title: string
  category: string
  player_editable: boolean
  important: boolean
  impact: string
  variables: string[]
  overridden: boolean
}

export interface PromptTemplate extends PromptTemplateSummary {
  default_content: string
  content: string
}

async function list(base: string): Promise<PromptTemplateSummary[]> {
  const { data } = await axios.get<{ templates: PromptTemplateSummary[] }>(base)
  return data.templates
}

async function get(base: string, name: string): Promise<PromptTemplate> {
  const { data } = await axios.get<PromptTemplate>(base + '/' + encodeURIComponent(name))
  return data
}

async function put(base: string, name: string, content: string): Promise<PromptTemplate> {
  const { data } = await axios.put<PromptTemplate>(
    base + '/' + encodeURIComponent(name), { content },
  )
  return data
}

export const listPlayerPromptTemplates = () => list('/api/v1/prompt-templates')
export const getPlayerPromptTemplate = (name: string) => get('/api/v1/prompt-templates', name)
export const putPlayerPromptTemplate = (name: string, content: string) => put('/api/v1/prompt-templates', name, content)

export const listAdminPromptTemplates = () => list('/api/v1/admin/prompt-templates')
export const getAdminPromptTemplate = (name: string) => get('/api/v1/admin/prompt-templates', name)
export const putAdminPromptTemplate = (name: string, content: string) => put('/api/v1/admin/prompt-templates', name, content)
