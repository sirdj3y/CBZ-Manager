import client from './client'

export const libraryApi = {
  getSeries: (showHidden = false) => client.get('/api/series', { params: { show_hidden: showHidden } }),
  getSeriesDetail: (id) => client.get(`/api/series/${id}`),
  deleteSeries: (id) => client.delete(`/api/series/${id}`),
  toggleSeriesHidden: (id) => client.patch(`/api/series/${id}/hidden`),
  setSeriesCover: (id, tomeId) => client.patch(`/api/series/${id}/cover`, { tome_id: tomeId }),
  deleteSeries: (id) => client.delete(`/api/series/${id}`),
  startScan: () => client.post('/api/scan'),
  getScanStatus: (jobId) => client.get(`/api/scan/${jobId}`),
  getLastScan: () => client.get('/api/scan/last'),
  updateSeriesMetadata: (id, data) => client.put(`/api/series/${id}/metadata`, data),
  getAuthors: () => client.get('/api/library/authors'),
}
