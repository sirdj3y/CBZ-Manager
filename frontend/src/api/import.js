import client from './client'

export const importApi = {
  getSeries: () => client.get('/api/import/series'),
  parseFilename: (filename) => client.post('/api/import/parse', { filename }),

  checkFile: (filename, seriesId, newSeriesName) => {
    const form = new FormData()
    form.append('filename', filename)
    if (seriesId != null) form.append('series_id', seriesId)
    if (newSeriesName) form.append('new_series_name', newSeriesName)
    return client.post('/api/import/check', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  lookupTomes: (filepaths) => client.post('/api/import/lookup-tomes', { filepaths }),

  getImageSize: (file) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return client.post('/api/import/image-size', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  uploadFile: (file, filename, seriesId, newSeriesName, metadata = {}, onProgress) => {
    const form = new FormData()
    form.append('file', file, filename)
    form.append('filename', filename)
    if (seriesId != null) form.append('series_id', seriesId)
    if (newSeriesName) form.append('new_series_name', newSeriesName)
    if (metadata && Object.keys(metadata).some(k => metadata[k]))
      form.append('metadata', JSON.stringify(metadata))
    return client.post('/api/import/file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    })
  },
}
