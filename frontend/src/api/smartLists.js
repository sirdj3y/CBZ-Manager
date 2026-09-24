import client from './client'

export const smartListsApi = {
  list: () => client.get('/api/smart-lists'),
  fields: () => client.get('/api/smart-lists/fields'),
  tomes: (id) => client.get(`/api/smart-lists/${id}/tomes`),
  series: (id) => client.get(`/api/smart-lists/${id}/series`),
  create: (data) => client.post('/api/smart-lists', data),
  update: (id, data) => client.patch(`/api/smart-lists/${id}`, data),
  remove: (id) => client.delete(`/api/smart-lists/${id}`),
  duplicate: (id) => client.post(`/api/smart-lists/${id}/duplicate`),
  reorder: (ids) => client.patch('/api/smart-lists/reorder', { ids }),
}
