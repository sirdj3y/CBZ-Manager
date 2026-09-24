import client from './client'

export const scraperApi = {
  searchGoogleBooks: (query, series, number, author) =>
    client.post('/api/scrape/googlebooks', { query, series, number, author }),
  searchComicVine: (query, series) =>
    client.post('/api/scrape/comicvine', { query, series }),
  searchBedetheque: (query, series, seriesId) =>
    client.post('/api/scrape/bedetheque', { query, series, series_id: seriesId }),
  bedethequeBulk: (url, seriesId) =>
    client.post('/api/scrape/bedetheque-bulk', { url, series_id: seriesId }),
  bedethequeSuggest: (name) =>
    client.post('/api/scrape/bedetheque-suggest', { name }),
  bedethequeAlbumSummary: (url) =>
    client.post('/api/scrape/bedetheque-album-summary', { url }),
}
