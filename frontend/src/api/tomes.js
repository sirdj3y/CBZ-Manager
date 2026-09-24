import client from './client'

export const tomesApi = {
  getTome: (id) => client.get(`/api/tomes/${id}`),
  getMetadata: (id) => client.get(`/api/tomes/${id}/metadata`),
  updateMetadata: (id, data, silent = false) => client.put(`/api/tomes/${id}/metadata`, data, { params: silent ? { silent: true } : {} }),
  parseFilename: (id) => client.post(`/api/tomes/${id}/parse-filename`),
  updateUserData: (id, data) => client.patch(`/api/tomes/${id}/user-data`, data),
  getTags: () => client.get('/api/tomes/tags'),
  getProgress: (id) => client.get(`/api/tomes/${id}/progress`),
  saveProgress: (id, last_page) => client.put(`/api/tomes/${id}/progress`, { last_page }),
  getInProgress: () => client.get('/api/tomes/in-progress'),
  getRecent: (limit = 20) => client.get('/api/tomes/recent', { params: { limit } }),
  rename: (id, pattern) => client.post(`/api/tomes/${id}/rename`, { pattern }),
  renameBulk: (ids, pattern) => client.post('/api/tomes/rename-bulk', { ids, pattern }),
  renameToName: (id, newFilename) => client.post(`/api/tomes/${id}/rename-to`, { new_filename: newFilename }),
  renameBulkToNames: (renames) => client.post('/api/tomes/rename-bulk-to', { renames }),
  toggleHidden: (id) => client.patch(`/api/tomes/${id}/hidden`),
  toggleOneshot: (id) => client.patch(`/api/tomes/${id}/oneshot`),
  deleteFile: (id) => client.delete(`/api/tomes/${id}/file`),
  getFileInfo: (id) => client.get(`/api/tomes/${id}/file-info`),
  moveTomes: (tomeIds, targetSeriesId) => client.post('/api/tomes/move', { tome_ids: tomeIds, target_series_id: targetSeriesId }),
  deleteBulk: (tomeIds) => client.post('/api/tomes/delete-bulk', { tome_ids: tomeIds }),
  updateMetadataBulk: (tomeIds, fields) => client.put('/api/tomes/metadata-bulk', { tome_ids: tomeIds, fields }),
  // Navigation directe (pas d'appel axios) — le navigateur gère le téléchargement en
  // flux nativement, sans charger le fichier en mémoire côté JS.
  downloadUrl: (id) => `/api/tomes/${id}/download`,
  downloadBulkUrl: (tomeIds) => `/api/tomes/download-bulk?${tomeIds.map(id => `tome_ids=${id}`).join('&')}`,
}
