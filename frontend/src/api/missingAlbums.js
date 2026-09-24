import client from './client'

export const missingAlbumsApi = {
  list: () => client.get('/api/missing-albums'),
  listSeries: () => client.get('/api/missing-albums/series'),
  toggleTracking: (seriesId, trackNewAlbums) =>
    client.put(`/api/missing-albums/series/${seriesId}/track`, { track_new_albums: trackNewAlbums }),
  lastScan: () => client.get('/api/missing-albums/scan/last'),
  scanStatus: (jobId) => client.get(`/api/missing-albums/scan/${jobId}`),
  startScan: () => client.post('/api/missing-albums/scan'),
  count: () => client.get('/api/missing-albums/count'),
  ignore: (missingAlbumId) => client.post(`/api/missing-albums/${missingAlbumId}/ignore`),
  fulfilled: (missingAlbumId) => client.post(`/api/missing-albums/${missingAlbumId}/fulfilled`),
  listIgnored: () => client.get('/api/missing-albums/ignored'),
  unignore: (ignoredId) => client.delete(`/api/missing-albums/ignored/${ignoredId}`),
  setBedethequeUrl: (seriesId, url) =>
    client.put(`/api/missing-albums/series/${seriesId}/bedetheque-url`, { url }),
  setBedethequeStatus: (seriesId, status) =>
    client.put(`/api/missing-albums/series/${seriesId}/bedetheque-status`, { status }),
  recheckSeries: (seriesId) => client.post(`/api/missing-albums/series/${seriesId}/recheck`),
}
