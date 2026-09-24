// Runs `worker` over `items` with at most `limit` calls in flight at once —
// unlike Promise.all(items.map(worker)), which fires every call simultaneously
// regardless of how many items there are.
export async function mapWithConcurrency(items, limit, worker) {
  const results = new Array(items.length)
  let next = 0

  async function run() {
    while (next < items.length) {
      const i = next++
      results[i] = await worker(items[i], i)
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run))
  return results
}
