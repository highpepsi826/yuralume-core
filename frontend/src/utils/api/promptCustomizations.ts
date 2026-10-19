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
  has_draft: boolean
}

export interface PromptTemplate extends PromptTemplateSummary {
  default_content: string
  content: string
  draft_content: string
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

async function remove(base: string, name: string): Promise<PromptTemplate> {
  const { data } = await axios.delete<PromptTemplate>(base + '/' + encodeURIComponent(name) + '/draft')
  return data
}

async function publish(base: string, name: string): Promise<PromptTemplate> {
  const { data } = await axios.post<PromptTemplate>(base + '/' + encodeURIComponent(name) + '/publish-draft')
  return data
}

export const listPlayerPromptTemplates = () => list('/api/v1/prompt-templates')
export const getPlayerPromptTemplate = (name: string) => get('/api/v1/prompt-templates', name)
export const putPlayerPromptTemplate = (name: string, content: string) => put('/api/v1/prompt-templates', name, content)
export const putPlayerPromptTemplateDraft = (name: string, content: string) => put('/api/v1/prompt-templates', name + '/draft', content)
export const deletePlayerPromptTemplateDraft = (name: string) => remove('/api/v1/prompt-templates', name)
export const publishPlayerPromptTemplateDraft = (name: string) => publish('/api/v1/prompt-templates', name)

export const listAdminPromptTemplates = () => list('/api/v1/admin/prompt-templates')
export const getAdminPromptTemplate = (name: string) => get('/api/v1/admin/prompt-templates', name)
export const putAdminPromptTemplate = (name: string, content: string) => put('/api/v1/admin/prompt-templates', name, content)
export const putAdminPromptTemplateDraft = (name: string, content: string) => put('/api/v1/admin/prompt-templates', name + '/draft', content)
export const deleteAdminPromptTemplateDraft = (name: string) => remove('/api/v1/admin/prompt-templates', name)
export const publishAdminPromptTemplateDraft = (name: string) => publish('/api/v1/admin/prompt-templates', name)
