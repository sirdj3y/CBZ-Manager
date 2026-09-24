import client from './client'

export const profilesApi = {
  list: () => client.get('/api/profiles'),
  permissions: () => client.get('/api/profiles/permissions'),
  create: (payload) => client.post('/api/profiles', payload),
  update: (id, payload) => client.put(`/api/profiles/${id}`, payload),
  remove: (id) => client.delete(`/api/profiles/${id}`),
}
