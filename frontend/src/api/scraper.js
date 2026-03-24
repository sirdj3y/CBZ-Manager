import client from './client'

export const scraperApi = {
  searchGoogleBooks: (query, series, number, author) =>
    client.post('/api/scrape/googlebooks', { query, series, number, author }),
  searchComicVine: (query, series) =>
    client.post('/api/scrape/comicvine', { query, series }),
}
