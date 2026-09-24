<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { tomesApi } from '../../api/tomes'
import { libraryApi } from '../../api/library'
import { missingAlbumsApi } from '../../api/missingAlbums'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'
import TagInput from '../ui/TagInput.vue'
import SvgIcon from '../SvgIcon.vue'

const props = defineProps({
  series: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved', 'deleted', 'enrich'])

const notif = useNotificationStore()
const library = useLibraryStore()
const form = ref({ Series: '', Publisher: '', Writer: '', Penciller: '', LanguageISO: '' })
const originalForm = ref(null)
const bedethequeUrl = ref('')
const originalBedethequeUrl = ref('')
const bedethequeStatus = ref('')
const originalBedethequeStatus = ref('')
const bedethequeResume = ref('')
const originalBedethequeResume = ref('')
const classification = ref('')
const originalClassification = ref('')
const classifications = ref([])
const ageRating = ref('')
const originalAgeRating = ref('')
const ageRatings = ref([])
const saving = ref(false)
const confirmDelete = ref(false)
const deleting = ref(false)
// Menu "⋮" du header — regroupe les actions destructives/secondaires (Supprimer la série),
// pour ne pas les laisser à portée de clic en permanence dans le footer sur les 2 onglets.
const showHeaderMenu = ref(false)
const headerMenuRef = ref(null)
function onDocClick(e) {
  if (showHeaderMenu.value && headerMenuRef.value && !headerMenuRef.value.contains(e.target)) {
    showHeaderMenu.value = false
  }
}

// Onglets — "Détails" fusionné dans "Série" (retour utilisateur : pas besoin d'un onglet à
// part pour 4 champs). "Images" reste séparé : upload de fichiers, nature différente du
// reste du formulaire.
const TABS = [
  { key: 'series', label: 'Série' },
  { key: 'images', label: 'Images' },
]
const activeTab = ref('series')

// ── Images "hero" (fond/logo/personnage) — upload immédiat, même principe que la photo de
// profil (AccountView.vue) : pas rattaché au bouton "Appliquer" du formulaire, qui ne
// concerne que les champs ComicInfo.xml/Classification/Public. Compteurs de version locaux
// (initialisés depuis la prop, puis mis à jour après chaque upload/suppression) pour que
// l'aperçu et le cache-busting de l'URL réagissent sans devoir recharger toute la modale.
// Personnage détouré retiré (idée abandonnée) — Fond/Logo seuls restent proposés ici.
const HERO_KINDS = [
  { kind: 'background', label: 'Fond', hint: 'ex. 1600×600px' },
  { kind: 'logo', label: 'Logo', hint: '~600px de haut' },
]
const heroVersions = ref({
  background: props.series.hero_background_version || 0,
  logo: props.series.hero_logo_version || 0,
})
const heroUploading = ref({ background: false, logo: false })
const heroFileInputs = ref({})
// Le compteur de version indique qu'une image a été fournie un jour, pas qu'elle existe
// encore sur disque (même filet de sécurité que SeriesDetailView.vue::heroBgError) — sans
// ça un fichier manquant affichait le texte alternatif brut ("Fond"/"Logo") à la place de
// l'aperçu, comme vu sur la fiche avant ce correctif.
const heroImageErrors = ref({ background: false, logo: false })

function heroImageUrl(kind) {
  const v = heroVersions.value[kind]
  return v > 0 && !heroImageErrors.value[kind] ? libraryApi.heroImageUrl(props.series.id, kind, v) : null
}

function pickHeroImage(kind) {
  heroFileInputs.value[kind]?.click()
}

async function onHeroImageSelected(kind, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  heroUploading.value[kind] = true
  try {
    const { data } = await libraryApi.uploadSeriesHero(props.series.id, kind, file)
    heroVersions.value[kind] = data[`hero_${kind}_version`]
    heroImageErrors.value[kind] = false
    notif.success('Image mise à jour')
    emit('saved')
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'envoi de l'image")
  } finally {
    heroUploading.value[kind] = false
  }
}

async function removeHeroImage(kind) {
  heroUploading.value[kind] = true
  try {
    const { data } = await libraryApi.deleteSeriesHero(props.series.id, kind)
    heroVersions.value[kind] = data[`hero_${kind}_version`]
    heroImageErrors.value[kind] = false
    notif.success('Image supprimée')
    emit('saved')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    heroUploading.value[kind] = false
  }
}

// Pool commun writers + pencillers (dédupliqué), même logique que MetadataDrawer
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

// Dessinateur/Scénariste/Éditeur en badges (TagInput) plutôt qu'un texte comma-séparé libre —
// chaque entrée passe par l'autocomplétion plutôt qu'être tapée à la main, moins de dérive de
// format (virgule sans espace, variante d'orthographe) qui créerait un doublon invisible
// ailleurs dans l'app. form.Penciller/Writer/Publisher restent des chaînes (c'est le format
// attendu par l'API/ComicInfo.xml) — ces computed ne font que convertir en tableau pour
// l'affichage, la valeur réellement envoyée à save() ne change pas.
function tagsField(key) {
  return computed({
    get: () => (form.value[key] || '').split(',').map(s => s.trim()).filter(Boolean),
    set: (arr) => { form.value[key] = arr.join(', ') },
  })
}
const pencillerTags = tagsField('Penciller')
const writerTags = tagsField('Writer')
const publisherTags = tagsField('Publisher')

onMounted(async () => {
  if (!library.authorNames.writers.length) library.fetchAuthors()
  if (props.series.tomes?.length) {
    try {
      const { data } = await tomesApi.getMetadata(props.series.tomes[0].id)
      form.value.Series      = data.Series      || props.series.name
      form.value.LanguageISO = data.LanguageISO || ''
    } catch {
      form.value.Series = props.series.name
    }
  } else {
    form.value.Series = props.series.name
  }
  // Auteurs/éditeur agrégés sur TOUS les tomes de la série (pas seulement le premier) —
  // un album peut avoir plusieurs scénaristes/dessinateurs, jusqu'ici invisibles ici dès
  // que le premier tome n'avait pas le champ renseigné.
  form.value.Publisher = (props.series.publishers || []).join(', ')
  form.value.Writer    = (props.series.writers || []).join(', ')
  form.value.Penciller = (props.series.pencillers || []).join(', ')
  bedethequeUrl.value = props.series.bedetheque_url || ''
  originalBedethequeUrl.value = bedethequeUrl.value
  bedethequeStatus.value = props.series.bedetheque_status || ''
  originalBedethequeStatus.value = bedethequeStatus.value
  // Normalement rempli par le scraper Bedetheque (voir openEnrich) — désormais aussi
  // modifiable/saisissable à la main, pour les séries qu'il ne trouve pas.
  bedethequeResume.value = props.series.bedetheque_resume || ''
  originalBedethequeResume.value = bedethequeResume.value
  classification.value = props.series.classification || ''
  originalClassification.value = classification.value
  try {
    const { data } = await libraryApi.getClassifications()
    classifications.value = data
  } catch { /* pas bloquant */ }
  ageRating.value = props.series.age_rating || ''
  originalAgeRating.value = ageRating.value
  try {
    const { data } = await libraryApi.getAgeRatings()
    ageRatings.value = data
  } catch { /* pas bloquant */ }
  // Snapshot après le pré-remplissage — permet à save() de sauter la réécriture de tous les
  // CBZ de la série (coûteuse en I/O) quand seuls l'URL et/ou le statut Bedetheque ont changé.
  originalForm.value = { ...form.value }
  window.addEventListener('keydown', onKey)
  window.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('click', onDocClick)
})

function onKey(e) {
  if (e.key === 'Escape') {
    // Un Échap doit d'abord fermer la couche visible au-dessus, pas toute la modale par-dessus
    // (qui perdrait les modifications en cours sans prévenir).
    if (confirmDelete.value) { confirmDelete.value = false; return }
    if (showHeaderMenu.value) { showHeaderMenu.value = false; return }
    emit('close')
  } else if (e.key === 'Enter' && !confirmDelete.value && !saving.value) {
    save()
  }
}

async function deleteSeries() {
  deleting.value = true
  try {
    await libraryApi.deleteSeries(props.series.id)
    notif.success('Série supprimée')
    emit('deleted', props.series.id)
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

// Champ interne (pas du ComicInfo.xml) — appel séparé, seulement si modifié pour éviter
// de redéclencher une ré-analyse Bedetheque inutile à chaque sauvegarde.
async function saveBedethequeUrlIfChanged() {
  const trimmedUrl = bedethequeUrl.value.trim()
  if (trimmedUrl === originalBedethequeUrl.value) return true
  try {
    await missingAlbumsApi.setBedethequeUrl(props.series.id, trimmedUrl)
    originalBedethequeUrl.value = trimmedUrl
    return true
  } catch (e) {
    notif.error(e.response?.data?.detail || 'URL Bedetheque invalide')
    return false
  }
}

async function saveBedethequeStatusIfChanged() {
  if (bedethequeStatus.value === originalBedethequeStatus.value) return true
  try {
    await missingAlbumsApi.setBedethequeStatus(props.series.id, bedethequeStatus.value || null)
    originalBedethequeStatus.value = bedethequeStatus.value
    return true
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Statut invalide')
    return false
  }
}

async function save() {
  if (!props.series.tomes?.length) {
    notif.error('Aucun album dans cette série')
    return
  }
  saving.value = true
  const patch = {}
  if (form.value.Series.trim())      patch.Series      = form.value.Series.trim()
  if (form.value.Penciller.trim())   patch.Penciller   = form.value.Penciller.trim()
  if (form.value.Writer.trim())      patch.Writer      = form.value.Writer.trim()
  if (form.value.Publisher.trim())   patch.Publisher   = form.value.Publisher.trim()
  if (form.value.LanguageISO.trim()) patch.LanguageISO = form.value.LanguageISO.trim()
  // Classification : champ propre à l'app, jamais écrit dans les CBZ — le backend le sort
  // du body avant la boucle de réécriture ComicInfo.xml, donc l'envoyer seul (sans aucun
  // champ ComicInfo modifié) ne déclenche pas cette réécriture coûteuse.
  const classificationChanged = classification.value !== originalClassification.value
  if (classificationChanged) patch.classification = classification.value
  const ageRatingChanged = ageRating.value !== originalAgeRating.value
  if (ageRatingChanged) patch.age_rating = ageRating.value
  const bedethequeResumeChanged = bedethequeResume.value !== originalBedethequeResume.value
  if (bedethequeResumeChanged) patch.bedetheque_resume = bedethequeResume.value

  // Réécrit le ComicInfo.xml de CHAQUE tome CBZ de la série — coûteux (plusieurs secondes
  // sur une grosse série). Sauté si aucun de ces champs n'a réellement changé, sinon changer
  // uniquement l'URL ou le statut Bedetheque (champs séparés, sauvegardés juste après) paierait
  // toujours ce coût pour rien.
  const formChanged = !originalForm.value || Object.keys(form.value).some(
    key => form.value[key] !== originalForm.value[key]
  )

  let errors = 0
  if (formChanged || classificationChanged || ageRatingChanged || bedethequeResumeChanged) {
    try {
      const { data } = await libraryApi.updateSeriesMetadata(props.series.id, patch)
      errors = data.errors || 0
      originalClassification.value = classification.value
      originalAgeRating.value = ageRating.value
      originalBedethequeResume.value = bedethequeResume.value
      library.fetchAuthors()
    } catch {
      errors = 1
    }
  }

  const bedethequeOk = (await saveBedethequeUrlIfChanged()) && (await saveBedethequeStatusIfChanged())

  saving.value = false
  if (!bedethequeOk) {
    // Erreur déjà notifiée par saveBedethequeUrlIfChanged
  } else if (errors) {
    notif.error(`${errors} album(s) non mis à jour (erreur)`)
  } else {
    notif.success('Métadonnées de la série mises à jour')
  }
  emit('saved')
  emit('close')
}

async function openEnrich() {
  const ok = (await saveBedethequeUrlIfChanged()) && (await saveBedethequeStatusIfChanged())
  if (!ok) return
  emit('enrich')
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div class="modal-backdrop" @click="$emit('close')" />

    <!-- Modal -->
    <div class="modal-wrap">
      <div class="modal-box">
        <!-- Header -->
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">{{ series.name }}</p>
            <p class="modal-subtitle">Métadonnées de la série — appliqué à tous les tomes CBZ</p>
          </div>
          <!-- Menu "⋮" : regroupe les actions secondaires/destructives (Supprimer la série),
               plutôt qu'un bouton en texte visible en permanence dans le footer sur les 3
               onglets — un clic supplémentaire pour y accéder, moins de risque de clic
               accidentel sur une action irréversible. -->
          <div class="header-menu-wrap" ref="headerMenuRef">
            <button type="button" class="btn btn-ghost btn-icon btn-sm" title="Plus d'actions" @click="showHeaderMenu = !showHeaderMenu">
              <SvgIcon name="more-vertical" />
            </button>
            <div v-if="showHeaderMenu" class="header-menu">
              <button type="button" class="header-menu-item header-menu-danger" @click="showHeaderMenu = false; confirmDelete = true">
                <SvgIcon name="trash-2" class="header-menu-icon" /> Supprimer la série
              </button>
            </div>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <!-- Onglets -->
        <div class="modal-tabs">
          <button
            v-for="t in TABS" :key="t.key" type="button"
            :class="['modal-tab', { 'modal-tab-active': activeTab === t.key }]"
            @click="activeTab = t.key"
          >{{ t.label }}</button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <div v-if="activeTab === 'series'" class="meta-col">
            <!-- Informations principales -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Informations principales</div>
              </div>
              <div class="meta-field">
                <label class="form-label">Série</label>
                <input v-model="form.Series" type="text" class="form-control" placeholder="Nom de la série" />
              </div>
            </div>

            <!-- Auteurs -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Auteurs</div>
              </div>
              <div class="meta-field-row-3">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Scénariste</label>
                  <TagInput v-model="writerTags" :suggestions="authorPool" placeholder="Ajouter un scénariste…" />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Dessinateur</label>
                  <TagInput v-model="pencillerTags" :suggestions="authorPool" placeholder="Ajouter un dessinateur…" />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Éditeur</label>
                  <TagInput v-model="publisherTags" :suggestions="library.authorNames.publishers" placeholder="Ajouter un éditeur…" />
                </div>
              </div>
            </div>

            <!-- Détails de publication -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Détails de publication</div>
              </div>
              <div class="meta-field-row-2">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Langue (ISO)</label>
                  <input v-model="form.LanguageISO" type="text" class="form-control" placeholder="ex: fr" />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Statut</label>
                  <select v-model="bedethequeStatus" class="form-control">
                    <option value="">—</option>
                    <option value="Série en cours">Série en cours</option>
                    <option value="Série finie">Série finie</option>
                  </select>
                </div>
              </div>
              <div class="meta-field-row-2">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Classification</label>
                  <select v-model="classification" class="form-control">
                    <option value="">—</option>
                    <option v-for="c in classifications" :key="c" :value="c">{{ c }}</option>
                  </select>
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Public</label>
                  <select v-model="ageRating" class="form-control">
                    <option value="">—</option>
                    <option v-for="a in ageRatings" :key="a" :value="a">{{ a }}</option>
                  </select>
                </div>
              </div>
              <!-- Normalement rempli par "Compléter" (scraper Bedetheque) — désormais aussi
                   saisissable à la main pour les séries qu'il ne trouve pas. -->
              <div class="meta-field">
                <label class="form-label">Résumé</label>
                <textarea v-model="bedethequeResume" class="form-control form-textarea" rows="3" placeholder="Résumé de la série…"></textarea>
              </div>
            </div>

            <!-- Fiche Bedetheque — champ + bouton sur la même ligne pour gagner de la place,
                 même principe que la popup album : le bouton reste teinté vermillon pour se
                 distinguer nettement du champ blanc à côté. -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Fiche Bedetheque</div>
              </div>
              <div class="meta-field-row">
                <div class="meta-field meta-field-grow">
                  <div class="url-search-wrap">
                    <input v-model="bedethequeUrl" type="url" class="form-control url-search-input" placeholder="https://www.bedetheque.com/serie-…" />
                    <a v-if="bedethequeUrl" :href="bedethequeUrl" target="_blank" rel="noopener" class="url-icon-btn url-visit-link" title="Consulter la fiche"><SvgIcon name="square-arrow-out-up-right" /></a>
                  </div>
                </div>
                <button type="button" class="btn-bedetheque" @click="openEnrich">
                  <SvgIcon name="search" class="btn-icon-svg" /> Compléter
                </button>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'images'" class="meta-col">
            <!-- Upload immédiat (pas rattaché au bouton "Appliquer"), même principe que la
                 photo de profil (AccountView.vue). Optionnelles : sans elles, la fiche
                 retombe sur un dégradé + titre texte (voir design-tests/ et heroGradient.js). -->
            <div class="meta-field">
              <div class="hero-image-row" v-for="h in HERO_KINDS" :key="h.kind">
                <div class="hero-image-info">
                  <span class="hero-image-label">{{ h.label }}</span>
                  <span class="hero-image-hint">{{ h.hint }}</span>
                </div>
                <!-- role="button" plutôt qu'un vrai <button> : contient elle-même le bouton
                     Supprimer, et un <button> ne peut pas contenir un autre élément
                     interactif (HTML invalide, casserait le nesting). -->
                <div
                  class="hero-image-preview"
                  :class="[`hero-image-preview-${h.kind}`, { 'hero-image-preview-empty': !heroImageUrl(h.kind), 'hero-image-preview-disabled': heroUploading[h.kind] }]"
                  role="button" :tabindex="heroUploading[h.kind] ? -1 : 0"
                  :aria-disabled="heroUploading[h.kind]"
                  :title="heroImageUrl(h.kind) ? 'Remplacer' : 'Importer'"
                  @click="!heroUploading[h.kind] && pickHeroImage(h.kind)"
                  @keydown.enter.space.prevent="!heroUploading[h.kind] && pickHeroImage(h.kind)"
                >
                  <img v-if="heroImageUrl(h.kind)" :src="heroImageUrl(h.kind)" :alt="h.label" @error="heroImageErrors[h.kind] = true">
                  <SvgIcon v-else name="image" class="hero-image-placeholder-icon" />
                  <span v-if="heroUploading[h.kind]" class="hero-image-uploading">Envoi…</span>
                  <button
                    v-if="heroImageUrl(h.kind) && !heroUploading[h.kind]" type="button" class="hero-image-remove-btn"
                    title="Supprimer" @click.stop="removeHeroImage(h.kind)"
                  >
                    <SvgIcon name="trash-2" />
                  </button>
                </div>
                <input :ref="el => { if (el) heroFileInputs[h.kind] = el }" type="file" accept="image/*" class="visually-hidden" @change="onHeroImageSelected(h.kind, $event)">
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Sauvegarde…' : 'Appliquer' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Popup confirmation suppression -->
    <div v-if="confirmDelete" class="confirm-backdrop" @click.self="confirmDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer la série ?</p>
        <p class="confirm-desc"><strong>{{ series.name }}</strong> et tous ses fichiers seront supprimés définitivement.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteSeries" :disabled="deleting">
            {{ deleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: var(--overlay-bg);
}

.modal-wrap {
  position: fixed;
  inset: 0;
  z-index: 201;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  pointer-events: none;
}

.modal-box {
  pointer-events: auto;
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%;
  /* Alignée sur la largeur de la popup album — mêmes cartes de section, même largeur. */
  max-width: 700px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header-info { flex: 1; min-width: 0; }
.modal-title {
  font-size: 0.95rem; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.modal-subtitle { font-size: 0.76rem; color: var(--muted); margin-top: 2px; }

/* Menu "⋮" du header */
.header-menu-wrap { position: relative; flex-shrink: 0; }
.header-menu {
  position: absolute; top: calc(100% + 4px); right: 0; z-index: 10;
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius-sm); box-shadow: var(--shadow-lg);
  min-width: 180px; overflow: hidden;
}
.header-menu-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: none; border: none; cursor: pointer; text-align: left;
  padding: 9px 12px; font-size: 0.8125rem; font-family: var(--font); color: var(--text);
}
.header-menu-item:hover { background: var(--light); }
.header-menu-danger { color: var(--danger); }
.header-menu-danger:hover { background: var(--danger-bg-light); }
.header-menu-icon { width: 15px; height: 15px; flex-shrink: 0; }

/* Onglets */
.modal-tabs {
  display: flex; gap: 2px;
  padding: 8px 16px 0;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-tab {
  background: none; border: none; cursor: pointer;
  padding: 7px 12px;
  font-size: 0.8125rem; font-weight: 600; font-family: var(--font); color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.12s, border-color 0.12s;
}
.modal-tab:hover { color: var(--text); }
.modal-tab-active { color: var(--vermilion); border-bottom-color: var(--vermilion); }

.modal-body {
  flex: 1; overflow-y: auto;
  padding: 14px 20px 16px;
}

/* Cartes par section (même principe que la popup album), chacune pleine largeur. */
@media (max-width: 720px) {
  .meta-field-row-3, .meta-field-row-2 { grid-template-columns: 1fr !important; }
}
.form-section {
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; display: flex; flex-direction: column; gap: 12px;
}
.form-section-title { display: flex; align-items: center; gap: 12px; }
.form-section-name { font-size: 0.9rem; font-weight: 700; color: var(--text); }
.meta-field-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; align-items: start; }
.meta-field-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: start; }

.meta-col { display: flex; flex-direction: column; gap: 11px; min-width: 0; }
.meta-field { display: flex; flex-direction: column; gap: 3px; }
.meta-field-row { display: flex; align-items: flex-end; gap: 10px; }
.meta-field-grow { flex: 1; min-width: 0; }

/* Libellés et placeholders allégés — même traitement que la popup album, pour ne pas
   alourdir une popup déjà dense en champs. */
.meta-col .form-label { font-size: 0.72rem; font-weight: 500; color: var(--muted); margin-bottom: 3px; }
.meta-col .form-control::placeholder,
.meta-col .form-textarea::placeholder { color: var(--placeholder); opacity: 0.75; }

.form-textarea { resize: vertical; font-family: var(--font); line-height: 1.5; min-height: 64px; }

/* Fiche Bedetheque — icône "Consulter" discrète dans le champ, visible au survol/focus
   uniquement (secondaire par rapport à "Compléter", à côté). */
.url-search-wrap { position: relative; }
.url-search-input { width: 100%; padding-right: 34px; }
.url-icon-btn {
  position: absolute; top: 50%; right: 4px; transform: translateY(-50%);
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: var(--radius-sm);
  background: none; border: none; color: var(--vermilion); cursor: pointer;
  opacity: 0; pointer-events: none;
  transition: background 0.12s, opacity 0.12s;
}
.url-icon-btn:hover { background: var(--surface); }
.url-search-wrap:hover .url-icon-btn,
.url-search-wrap:focus-within .url-icon-btn { opacity: 1; pointer-events: auto; }

/* Bouton "Compléter" — teinté vermillon (même palette que les badges TagInput) pour se
   détacher nettement du champ texte juste à côté. */
.btn-bedetheque {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  flex-shrink: 0; white-space: nowrap;
  padding: 0 14px; height: 34px; border-radius: var(--radius-sm); border: none; cursor: pointer;
  background: var(--vermilion-light); color: var(--vermilion);
  font-family: var(--font); font-size: 0.8125rem; font-weight: 600;
  transition: background 0.12s, color 0.12s;
}
.btn-bedetheque:hover { background: var(--vermilion); color: #fff; }

.modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

/* Images "hero" — un cadre d'aperçu par type (Fond/Logo), pleine largeur de la modale pour
   laisser assez de place à une image large (les deux sont recommandées en format paysage),
   cliquable dans son intégralité pour importer/remplacer (pas de bandeau d'actions séparé)
   — seul "Supprimer" reste un bouton distinct (icône en coin, visible au survol), puisqu'il
   n'a pas de sens sur tout le cadre. Toujours en "contain" (jamais rogné) : montrer l'image
   telle qu'elle sera utilisée en vignette (cover) ne sert à rien ici, l'utilisateur a besoin
   de voir le fichier entier qu'il vient d'envoyer. Logo sur fond quadrillé pour montrer la
   transparence PNG. */
.hero-image-row { display: flex; flex-direction: column; gap: 8px; }
.hero-image-row + .hero-image-row { margin-top: 16px; }
.hero-image-preview {
  position: relative; width: 100%; height: 130px;
  border-radius: var(--radius-sm); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; background: var(--light);
  cursor: pointer; padding: 0;
  transition: border-color 0.12s;
}
.hero-image-preview:hover,
.hero-image-preview:focus-visible {
  border-color: var(--vermilion);
  outline: none;
}
.hero-image-preview-disabled { cursor: default; }
.hero-image-preview-disabled:hover { border-color: var(--border); }
/* Quadrillage réservé au cadre qui affiche réellement une image transparente — sur le
   placeholder vide (pas encore d'image), les deux cadres doivent avoir le même fond neutre,
   sinon "Fond" ressort visuellement différent de "Logo" sans raison. */
.hero-image-preview-logo:not(.hero-image-preview-empty) {
  background-image:
    linear-gradient(45deg, var(--border) 25%, transparent 25%, transparent 75%, var(--border) 75%),
    linear-gradient(45deg, var(--border) 25%, transparent 25%, transparent 75%, var(--border) 75%);
  background-size: 10px 10px; background-position: 0 0, 5px 5px;
  background-color: var(--light);
}
.hero-image-preview img { width: 100%; height: 100%; object-fit: contain; padding: 8px; }
.hero-image-placeholder-icon { font-size: 1.6rem; color: var(--placeholder); }
.hero-image-remove-btn {
  position: absolute; top: 6px; right: 6px; z-index: 1;
  background: rgba(30,42,66,.72); border: none; padding: 5px; cursor: pointer;
  color: #fff; border-radius: var(--radius-sm); font-size: 0.8rem;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.12s;
}
.hero-image-preview:hover .hero-image-remove-btn,
.hero-image-remove-btn:focus-visible {
  opacity: 1;
}
.hero-image-remove-btn:hover { background: rgba(30,42,66,.9); }
.hero-image-uploading {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem; font-weight: 600; color: #fff; text-align: center;
  background: rgba(30,42,66,.72);
}
.hero-image-info { display: flex; align-items: baseline; gap: 8px; }
.hero-image-label { font-size: 0.8125rem; color: var(--text); font-weight: 600; }
.hero-image-hint { font-size: 0.72rem; color: var(--muted); }
.visually-hidden {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}

.confirm-backdrop {
  position: fixed; inset: 0; z-index: 300;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.confirm-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  padding: 24px; max-width: 400px; width: 100%;
}
.confirm-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.confirm-desc { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.confirm-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
