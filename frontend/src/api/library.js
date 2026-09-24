import client from './client'

export const libraryApi = {
  getSeries: (showHidden = false) => client.get('/api/series', { params: { show_hidden: showHidden } }),
  getSeriesDetail: (id) => client.get(`/api/series/${id}`),
  deleteSeries: (id) => client.delete(`/api/series/${id}`),
  deleteSeriesBulk: (seriesIds) => client.post('/api/series/delete-bulk', { series_ids: seriesIds }),
  toggleSeriesHidden: (id) => client.patch(`/api/series/${id}/hidden`),
  setSeriesCover: (id, tomeId) => client.patch(`/api/series/${id}/cover`, { tome_id: tomeId }),
  startScan: () => client.post('/api/scan'),
  getScanStatus: (jobId) => client.get(`/api/scan/${jobId}`),
  getLastScan: () => client.get('/api/scan/last'),
  updateSeriesMetadata: (id, data) => client.put(`/api/series/${id}/metadata`, data),
  getAuthors: () => client.get('/api/library/authors'),
  getAuthorDuplicates: () => client.get('/api/library/authors/duplicates'),
  mergeAuthors: (kind, sources, target) => client.post('/api/library/authors/merge', { kind, sources, target }),
  previewSeriesEnrich: (id) => client.get(`/api/series/${id}/enrich-preview`),
  applySeriesEnrich: (id, updates) => client.post(`/api/series/${id}/enrich-apply`, { updates }),
  getClassifications: () => client.get('/api/classifications'),
  getAgeRatings: () => client.get('/api/age-ratings'),
  heroImageUrl: (seriesId, kind, version) => `/api/series/${seriesId}/hero/${kind}${version ? `?v=${version}` : ''}`,
  uploadSeriesHero: (seriesId, kind, file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post(`/api/series/${seriesId}/hero/${kind}`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  deleteSeriesHero: (seriesId, kind) => client.delete(`/api/series/${seriesId}/hero/${kind}`),
}
