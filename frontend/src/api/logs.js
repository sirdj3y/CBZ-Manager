import client from './client'

export const logsApi = {
  get: () => client.get('/api/logs'),
  clear: () => client.delete('/api/logs'),
  alerts: () => client.get('/api/logs/alerts'),
}
