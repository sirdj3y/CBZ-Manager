import client from './client'

export const notificationsApi = {
  get: () => client.get('/api/notifications'),
  markSeen: () => client.post('/api/notifications/mark-seen'),
}
