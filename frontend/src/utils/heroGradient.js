// Repli sans image pour le bandeau "hero" (fiche série/album) : un dégradé purement CSS,
// construit avec les couleurs de l'app, choisi par un hash simple du nom de la série — pour
// que les fiches sans fond/logo fourni (l'immense majorité d'une bibliothèque réelle) ne se
// ressemblent pas toutes à l'identique. Testé et validé dans design-tests/ avant intégration.
const VARIANTS = ['a', 'b', 'c']

export function heroVariantFor(name) {
  let h = 0
  const s = name || ''
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return VARIANTS[h % VARIANTS.length]
}

// Deux jeux de dégradés : "wide" pour le grand bandeau de la fiche série (fond principal,
// plus marqué), "wash" pour la fiche album (juste une touche de couleur discrète, posée sur
// var(--surface) plutôt qu'en fond plein cadre — voir TomeDetailView.vue).
export const HERO_GRADIENTS_WIDE = {
  a: 'radial-gradient(120% 140% at 12% 8%, rgba(217,65,30,.30), transparent 58%), radial-gradient(110% 130% at 92% 105%, rgba(74,108,147,.34), transparent 62%)',
  b: 'radial-gradient(120% 140% at 90% 6%, rgba(74,108,147,.34), transparent 58%), radial-gradient(110% 130% at 6% 100%, rgba(233,196,106,.32), transparent 62%)',
  c: 'radial-gradient(120% 140% at 50% -6%, rgba(233,196,106,.36), transparent 55%), radial-gradient(110% 130% at 96% 92%, rgba(217,65,30,.26), transparent 60%)',
}

export const HERO_GRADIENTS_WASH = {
  a: 'radial-gradient(120% 160% at 100% 0%, rgba(217,65,30,.28), transparent 55%), radial-gradient(110% 140% at 100% 100%, rgba(74,108,147,.24), transparent 60%)',
  b: 'radial-gradient(120% 160% at 100% 0%, rgba(74,108,147,.28), transparent 55%), radial-gradient(110% 140% at 100% 100%, rgba(233,196,106,.26), transparent 60%)',
  c: 'radial-gradient(120% 160% at 100% 0%, rgba(233,196,106,.3), transparent 55%), radial-gradient(110% 140% at 100% 100%, rgba(217,65,30,.2), transparent 60%)',
}
