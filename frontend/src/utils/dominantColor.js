// Couleur dominante d'une cover — utilisée pour teinter le fond du hero (TomeDetailView.vue
// et SeriesDetailView.vue). Une simple moyenne de tous les pixels (approche précédente)
// donne presque toujours un gris/brun terne dès que l'image a plusieurs zones de couleurs
// différentes (fond, personnage, texte...) : ça ne "ressemble" à rien de reconnaissable sur
// la cover. On construit à la place un histogramme de couleurs quantifiées et on choisit le
// bucket le plus représentatif, en favorisant les teintes saturées et ni trop claires ni
// trop sombres — le blanc/noir de fond d'une cover, même très fréquent, ne représente pas
// visuellement l'image aux yeux d'un humain — sans les exclure totalement si rien d'autre ne
// ressort (fallback naturel via le score, jamais un cas particulier séparé).

const SAMPLE_SIZE = 32
const BUCKET_STEP = 24 // ~10-11 buckets par canal (256 / 24)

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  const d = max - min
  let s = 0
  if (d !== 0) s = d / (1 - Math.abs(2 * l - 1))
  return { s, l }
}

// Dessine l'image dans un petit canvas hors-écran et retourne {r,g,b} de la couleur la plus
// représentative, ou null (image absente, canvas "tainted" par une source cross-origin sans
// CORS, etc — purement décoratif, jamais bloquant).
export function extractDominantColor(imgEl) {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = SAMPLE_SIZE
    canvas.height = SAMPLE_SIZE
    const ctx = canvas.getContext('2d')
    ctx.drawImage(imgEl, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
    const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE)

    const buckets = new Map()
    for (let i = 0; i < data.length; i += 4) {
      // Bords arrondis anti-aliasés d'une cover PNG, par exemple — pixels quasi transparents
      // à ignorer, sinon ils tirent la moyenne du bucket vers le blanc.
      if (data[i + 3] < 200) continue
      const r = data[i], g = data[i + 1], b = data[i + 2]
      const key = (r / BUCKET_STEP | 0) + ',' + (g / BUCKET_STEP | 0) + ',' + (b / BUCKET_STEP | 0)
      let bucket = buckets.get(key)
      if (!bucket) {
        bucket = { count: 0, r: 0, g: 0, b: 0 }
        buckets.set(key, bucket)
      }
      bucket.count++
      bucket.r += r; bucket.g += g; bucket.b += b
    }
    if (!buckets.size) return null

    let best = null
    let bestScore = -1
    for (const bucket of buckets.values()) {
      const r = bucket.r / bucket.count
      const g = bucket.g / bucket.count
      const b = bucket.b / bucket.count
      const { s, l } = rgbToHsl(r, g, b)
      const saturationWeight = 0.15 + s * 0.85
      const lightnessWeight = Math.max(0.15, 1 - Math.abs(l - 0.5) * 1.4)
      const score = bucket.count * saturationWeight * lightnessWeight
      if (score > bestScore) {
        bestScore = score
        best = { r, g, b }
      }
    }
    return best
  } catch {
    return null
  }
}

export function rgbToCss({ r, g, b }) {
  return `${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}`
}

export function darkenRgbToCss({ r, g, b }, factor = 0.42) {
  return `${Math.round(r * factor)}, ${Math.round(g * factor)}, ${Math.round(b * factor)}`
}
