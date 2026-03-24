import client from './client'

export const settingsApi = {
  get: () => client.get('/api/settings'),
  update: (data) => client.put('/api/settings', data),
  browse: (path = '') => client.get('/api/settings/browse', { params: path ? { path } : {} }),
  about: () => client.get('/api/settings/about'),
  resetDb: () => client.delete('/api/settings/reset-db'),
}
