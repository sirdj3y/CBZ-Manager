import client from './client'

export const usersApi = {
  list: () => client.get('/api/users'),
  create: (payload) => client.post('/api/users', payload),
  update: (id, payload) => client.patch(`/api/users/${id}`, payload),
  remove: (id) => client.delete(`/api/users/${id}`),
  getHiddenSeries: (id) => client.get(`/api/users/${id}/hidden-series`),
  setHiddenSeries: (id, seriesIds) => client.put(`/api/users/${id}/hidden-series`, { series_ids: seriesIds }),
}
