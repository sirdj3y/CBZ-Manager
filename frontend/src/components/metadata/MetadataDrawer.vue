<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import ScraperModal from './ScraperModal.vue'
import StarRating from '../ui/StarRating.vue'
import TagInput from '../ui/TagInput.vue'
import SvgIcon from '../SvgIcon.vue'
import { tomesApi } from '../../api/tomes'
import { scraperApi } from '../../api/scraper'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'
import { useRouter } from 'vue-router'
import { formatTomeNumber } from '../../utils/renamePattern'
import Hint from '../ui/Hint.vue'

const props = defineProps({
  tome: { type: Object, required: true },
  // Ouvre directement la recherche multi-sources, sans passer par un clic supplémentaire
  // sur "Rechercher" — utilisé par le menu "…" des covers pour y accéder en un clic.
  openScraper: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const notif = useNotificationStore()
const library = useLibraryStore()
const router = useRouter()
const metadata = ref({})
const original = ref({})
const saving = ref(false)

const canEdit = props.tome.file_format === 'cbz'
const fileInfo = ref(null)

// Retour aux onglets et aux labels au-dessus des champs (essais "1 page + labels à gauche"
// puis "maquette corrigée" non concluants, retour utilisateur négatif) : "Album" = identité +
// crédits + champs techniques + fiche Bedetheque, "Métadonnées" = descriptif (Genre/Résumé) +
// annotations perso + infos fichier.
const TABS = [
  { key: 'album', label: 'Album' },
  { key: 'details', label: 'Métadonnées' },
]
const activeTab = ref('album')

function toTags(str) { return (str || '').split(',').map(s => s.trim()).filter(Boolean) }
function updateTags(key, arr) { metadata.value[key] = arr.join(', ') }

// Pool commun scénaristes + dessinateurs (dédupliqué), même logique que SeriesMetadataModal.
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

// Genre en badges (TagInput) — donnée réelle = chaîne comma-séparée (ComicInfo.xml),
// converti en tableau uniquement pour l'affichage.
const genreTags = computed(() => (metadata.value.Genre || '').split(',').map(s => s.trim()).filter(Boolean))

// Ouvert seulement une fois les métadonnées chargées (onMounted ci-dessous) — pas
// synchronement ici : ScraperModal lit props.series/props.number dans SON PROPRE onMounted,
// qui se déclenche avant celui du parent (les enfants montent avant leur parent). Ouvert
// d'emblée, il capturait donc systématiquement metadata.Series/Number encore vides,
// préremplissant la recherche à vide.
const showScraper = ref(false)
const confirmDelete = ref(false)
const deleting = ref(false)
// Menu "⋮" du header — regroupe les actions destructives/secondaires (Supprimer), pour ne
// pas les laisser à portée de clic en permanence.
const showHeaderMenu = ref(false)
const headerMenuRef = ref(null)
function onDocClick(e) {
  if (showHeaderMenu.value && headerMenuRef.value && !headerMenuRef.value.contains(e.target)) {
    showHeaderMenu.value = false
  }
  if (showAddFieldMenu.value && addFieldMenuRef.value && !addFieldMenuRef.value.contains(e.target)) {
    showAddFieldMenu.value = false
  }
}

// Sous-titre du header : TXX · Format · Taille — le nom de la série n'y figure plus (déjà son
// propre champ juste en dessous dans le formulaire, inutile de le répéter).
const headerSubtitle = computed(() => {
  const parts = []
  if (isOneshot.value) parts.push('One-shot')
  else if (props.tome.number) parts.push('T' + formatTomeNumber(props.tome.number))
  if (props.tome.file_format) parts.push(props.tome.file_format.toUpperCase())
  const size = props.tome.file_size ?? fileInfo.value?.file_size
  if (size) parts.push(fmtSize(size))
  return parts.join(' · ')
})

// Mois/Jour en menus déroulants plutôt qu'en texte libre — évite une valeur invalide (ex.
// "13" pour un mois), même donnée stockée (chaîne ComicInfo.xml) qu'avant.
const MONTHS = Array.from({ length: 12 }, (_, i) => String(i + 1))
const DAYS = Array.from({ length: 31 }, (_, i) => String(i + 1))

// Annotations utilisateur
const userRating = ref(props.tome.user_rating || 0)
const userTags = ref([...(props.tome.user_tags || [])])

// Champs ComicInfo.xml secondaires (StoryArc, Characters, Inker…) — existent tous côté
// backend/écriture XML mais quasi jamais renseignés en pratique, donc pas affichés par
// défaut (le formulaire serait illisible avec 20 champs vides). Visible dès qu'un champ a
// déjà une valeur (import externe, ancien fichier…) OU a été ajouté à la main via "Ajouter un
// champ" — pas besoin d'état à persister, la présence d'une valeur suffit à le refaire
// apparaître la prochaine fois.
const EXTRA_FIELDS = [
  { key: 'Volume', label: 'Volume' },
  { key: 'Format', label: 'Format (édition)' },
  { key: 'AlternateSeries', label: 'Série alternative' },
  { key: 'AlternateNumber', label: 'Numéro alternatif' },
  { key: 'StoryArc', label: 'Arc narratif' },
  { key: 'SeriesGroup', label: 'Groupe de séries' },
  { key: 'Characters', label: 'Personnages' },
  { key: 'Teams', label: 'Équipes' },
  { key: 'Locations', label: 'Lieux' },
  { key: 'Tags', label: 'Tags' },
  { key: 'Inker', label: 'Encreur' },
  { key: 'Colorist', label: 'Coloriste' },
  { key: 'Letterer', label: 'Lettreur' },
  { key: 'CoverArtist', label: 'Dessinateur de couverture' },
  { key: 'Editor', label: 'Éditeur (rédaction)' },
  { key: 'Translator', label: 'Traducteur' },
  { key: 'ScanInformation', label: 'Informations de scan' },
  { key: 'GTIN', label: 'GTIN' },
  { key: 'Notes', label: 'Notes' },
]
const manuallyAddedFields = ref([])
const visibleExtraFields = computed(() =>
  EXTRA_FIELDS.filter(f => metadata.value[f.key] || manuallyAddedFields.value.includes(f.key))
)
const hiddenExtraFields = computed(() =>
  EXTRA_FIELDS.filter(f => !visibleExtraFields.value.includes(f))
)
const showAddFieldMenu = ref(false)
const addFieldMenuRef = ref(null)
function addExtraField(key) {
  if (!manuallyAddedFields.value.includes(key)) manuallyAddedFields.value.push(key)
  showAddFieldMenu.value = false
}

// One-shot — bascule immédiate (comme le masquage ailleurs dans l'app), pas liée au bouton
// Sauvegarder : c'est un fait sur l'album, pas un champ de formulaire à valider.
const isOneshot = ref(!!props.tome.is_oneshot)
const togglingOneshot = ref(false)
async function toggleOneshot() {
  togglingOneshot.value = true
  try {
    const { data } = await tomesApi.toggleOneshot(props.tome.id)
    isOneshot.value = data.is_oneshot
    // Un one-shot n'a pas de numéro de tome — voir META_FIELDS/apply_pattern côté import/rename.
    if (isOneshot.value) metadata.value.Number = ''
    emit('saved')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la mise à jour')
  } finally {
    togglingOneshot.value = false
  }
}

onMounted(async () => {
  // Attach the Escape-to-close listener unconditionally — otherwise a failed load
  // below leaves the drawer stuck open with no way to dismiss it.
  window.addEventListener('keydown', onKey)
  window.addEventListener('click', onDocClick)
  if (!library.authorNames.writers.length) library.fetchAuthors()
  try {
    const [metaRes, infoRes] = await Promise.all([
      tomesApi.getMetadata(props.tome.id),
      tomesApi.getFileInfo(props.tome.id),
    ])
    metadata.value = { ...metaRes.data }
    original.value = { ...metaRes.data }
    fileInfo.value = infoRes.data
    if (props.openScraper) showScraper.value = true
  } catch {
    notif.error('Impossible de charger les métadonnées de cet album')
  }
})

function fmtSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' Go'
}

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('click', onDocClick)
})

function onKey(e) {
  // Touche tapée dans une couche shadcn ouverte depuis le tiroir (modale Scraper, menu…) :
  // elle la gère et se ferme seule — sinon Échap refermerait aussi le tiroir.
  if (e.target?.closest?.('[data-slot$="-content"]')) return
  if (e.key === 'Escape') {
    // Referme d'abord la couche visible au-dessus (scraper, menu ou confirmation de
    // suppression), jamais toute la modale directement — sinon des modifications en cours
    // seraient perdues sans prévenir simplement parce qu'une de ces couches était ouverte.
    if (showScraper.value) { showScraper.value = false; return }
    if (confirmDelete.value) { confirmDelete.value = false; return }
    if (showHeaderMenu.value) { showHeaderMenu.value = false; return }
    if (showAddFieldMenu.value) { showAddFieldMenu.value = false; return }
    emit('close')
  } else if (
    e.key === 'Enter' &&
    !showScraper.value && !confirmDelete.value && !saving.value &&
    e.target.tagName !== 'TEXTAREA'
  ) {
    // Le commentaire personnel est un textarea multi-lignes : Entrée doit y rester un
    // saut de ligne, pas déclencher la sauvegarde de toute la modale.
    save()
  }
}

function cancel() { metadata.value = { ...original.value }; emit('close') }

async function save() {
  saving.value = true
  try {
    // Sauvegarde métadonnées ComicInfo (CBZ seulement)
    if (canEdit) {
      const { data } = await tomesApi.updateMetadata(props.tome.id, metadata.value)
      metadata.value = { ...data }
      original.value = { ...data }
      library.fetchAuthors() // pool d'autocomplétion potentiellement obsolète (nouvel auteur, etc.)
    }
    // Sauvegarde annotations (tous formats)
    await tomesApi.updateUserData(props.tome.id, {
      user_rating: userRating.value || null,
      user_tags: userTags.value,
    })
    notif.success('Sauvegardé')
    emit('saved')
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la sauvegarde')
  } finally {
    saving.value = false
  }
}

async function deleteTome() {
  deleting.value = true
  try {
    const { data } = await tomesApi.deleteFile(props.tome.id)
    notif.success('Album supprimé')
    emit('deleted', { tome_id: props.tome.id, series_deleted: data.series_deleted, series_id: data.series_id })
    emit('close')
    if (data.series_deleted) router.push('/series')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

function applyScraperResult(result) {
  showScraper.value = false
  if (result.title) metadata.value.Title = result.title
  if (result.series) metadata.value.Series = result.series
  if (result.number) metadata.value.Number = formatTomeNumber(result.number)
  if (result.source === 'bedetheque' && result.authors?.length) {
    // Bedetheque distingue scénariste et dessinateur (contrairement à Google Books/ComicVine)
    metadata.value.Writer = result.authors[0] || ''
    metadata.value.Penciller = result.authors[1] || result.authors[0] || ''
  } else if (result.authors?.length) {
    metadata.value.Writer = result.authors.join(', ')
  }
  if (result.publisher) metadata.value.Publisher = result.publisher
  if (result.year) metadata.value.Year = result.year
  if (result.pages) metadata.value.PageCount = String(result.pages)
  if (result.isbn) metadata.value.ISBN = result.isbn
  // Web : lien vers la fiche de CET album précisément (pas juste la série) — permet un
  // lien direct depuis la page album plutôt que de retomber sur l'URL de la série.
  if (result.url) metadata.value.Web = result.url
  if (result.source === 'bedetheque' && result.rating != null) {
    metadata.value.CommunityRating = String(result.rating)
    metadata.value.bedetheque_votes = result.rating_count ?? null
  }
  // Résumé — seulement sur la page dédiée de l'album (jamais sur la page série déjà
  // récupérée pour le reste), donc une requête à part, en tâche de fond, sans bloquer le
  // reste du formulaire déjà rempli.
  if (result.source === 'bedetheque' && result.url) {
    scraperApi.bedethequeAlbumSummary(result.url)
      .then(({ data }) => { if (data.summary) metadata.value.Summary = data.summary })
      .catch(() => {})
  }
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
            <p class="modal-title">{{ tome.title || tome.filename }}</p>
            <p v-if="headerSubtitle" class="modal-subtitle">{{ headerSubtitle }}</p>
          </div>
          <!-- Menu "⋮" : regroupe les actions secondaires/destructives (Supprimer), plutôt
               qu'un bouton en texte visible en permanence dans le footer. -->
          <div class="header-menu-wrap" ref="headerMenuRef">
            <Hint label="Plus d'actions">
              <button type="button" class="btn btn-ghost btn-icon btn-sm" @click="showHeaderMenu = !showHeaderMenu">
                <SvgIcon name="more-vertical" />
              </button>
            </Hint>
            <div v-if="showHeaderMenu" class="header-menu">
              <button type="button" class="header-menu-item header-menu-danger" @click="showHeaderMenu = false; confirmDelete = true">
                <SvgIcon name="trash-2" class="header-menu-icon" /> Supprimer
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

        <!-- Body — "Album" = identité/crédits/champs techniques/fiche Bedetheque,
             "Métadonnées" = descriptif (Genre/Résumé)/annotations perso/infos fichier. -->
        <div class="modal-body">
          <div v-if="!canEdit" class="alert alert-warning modal-warning">
            ⚠ Les fichiers CBR sont en lecture seule. Convertissez en CBZ pour modifier.
          </div>

          <!-- Pas de carte "Couverture" : ça demanderait de choisir/remplacer la couverture
               d'un album précis, une fonctionnalité qui n'existe pas dans l'app (la
               couverture est toujours la première page du fichier, aucune route ne permet
               d'en choisir une autre ni d'en importer une) — pas assez utile pour justifier
               ce chantier (nouvelle colonne DB, endpoint d'upload, invalidation du cache)
               rien que pour cette popup. Sections en pleine largeur, plus de 2 colonnes. -->
          <div v-if="activeTab === 'album'" class="meta-col">
            <!-- Informations principales -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Informations principales</div>
              </div>
              <div class="meta-field">
                <label class="form-label">Série</label>
                <input
                  :value="metadata.Series || ''" :readonly="!canEdit" type="text" placeholder="Nom de la série…"
                  @input="metadata.Series = $event.target.value"
                  class="form-control" :class="{ readonly: !canEdit }"
                />
              </div>
              <div class="meta-field-row">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Titre <span class="required">*</span></label>
                  <input
                    :value="metadata.Title || ''" :readonly="!canEdit" type="text"
                    @input="metadata.Title = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  />
                </div>
                <div class="meta-field meta-field-number">
                  <label class="form-label">Numéro</label>
                  <input
                    :value="metadata.Number || ''" :readonly="!canEdit || isOneshot" type="text"
                    @input="metadata.Number = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit || isOneshot }"
                  />
                </div>
                <label class="oneshot-inline" title="Album indépendant, sans rapport avec les autres tomes du dossier">
                  <input type="checkbox" :checked="isOneshot" :disabled="togglingOneshot || !canEdit" @change="toggleOneshot" class="toggle-checkbox" />
                  <span>One-shot</span>
                </label>
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
                  <TagInput
                    :model-value="toTags(metadata.Writer)" :suggestions="authorPool" :readonly="!canEdit"
                    placeholder="Ajouter un scénariste…"
                    @update:model-value="updateTags('Writer', $event)"
                  />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Dessinateur</label>
                  <TagInput
                    :model-value="toTags(metadata.Penciller)" :suggestions="authorPool" :readonly="!canEdit"
                    placeholder="Ajouter un dessinateur…"
                    @update:model-value="updateTags('Penciller', $event)"
                  />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Éditeur</label>
                  <TagInput
                    :model-value="toTags(metadata.Publisher)" :suggestions="library.authorNames.publishers" :readonly="!canEdit"
                    placeholder="Ajouter un éditeur…"
                    @update:model-value="updateTags('Publisher', $event)"
                  />
                </div>
              </div>
            </div>

            <!-- Détails de publication -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Détails de publication</div>
              </div>
              <div class="meta-field-row-3">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Année</label>
                  <input
                    :value="metadata.Year || ''" :readonly="!canEdit" type="text" placeholder="Année"
                    @input="metadata.Year = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Mois</label>
                  <select
                    :value="metadata.Month || ''" :disabled="!canEdit"
                    @change="metadata.Month = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  >
                    <option value="">—</option>
                    <option v-for="m in MONTHS" :key="m" :value="m">{{ m }}</option>
                  </select>
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Jour</label>
                  <select
                    :value="metadata.Day || ''" :disabled="!canEdit"
                    @change="metadata.Day = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  >
                    <option value="">—</option>
                    <option v-for="d in DAYS" :key="d" :value="d">{{ d }}</option>
                  </select>
                </div>
              </div>
              <div class="meta-field-row-3">
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Pages</label>
                  <input
                    :value="metadata.PageCount || ''" :readonly="!canEdit" type="text"
                    @input="metadata.PageCount = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">Langue</label>
                  <input
                    :value="metadata.LanguageISO || ''" :readonly="!canEdit" type="text" placeholder="ex: fr"
                    @input="metadata.LanguageISO = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  />
                </div>
                <div class="meta-field meta-field-grow">
                  <label class="form-label">ISBN</label>
                  <input
                    :value="metadata.ISBN || ''" :readonly="!canEdit" type="text"
                    @input="metadata.ISBN = $event.target.value"
                    class="form-control" :class="{ readonly: !canEdit }"
                  />
                </div>
              </div>
            </div>

            <!-- Fiche Bedetheque -->
            <div class="form-section">
              <div class="form-section-title">
                <div class="form-section-name">Fiche Bedetheque</div>
              </div>
              <div class="meta-field-row">
                <div class="meta-field meta-field-grow">
                  <div class="url-search-wrap">
                    <input
                      :value="metadata.Web || ''" :readonly="!canEdit" type="url"
                      placeholder="https://www.bedetheque.com/BD-…"
                      @input="metadata.Web = $event.target.value"
                      class="form-control url-search-input" :class="{ readonly: !canEdit }"
                    />
                    <Hint v-if="metadata.Web" label="Consulter la fiche">
                      <a :href="metadata.Web" target="_blank" rel="noopener" class="url-icon-btn url-visit-link"><SvgIcon name="square-arrow-out-up-right" /></a>
                    </Hint>
                  </div>
                </div>
                <button type="button" class="btn-bedetheque" @click="showScraper = true">
                  <SvgIcon name="search" class="btn-icon-svg" /> Récupérer
                </button>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'details'" class="meta-col">
            <div class="meta-field">
              <label class="form-label">Genre</label>
              <TagInput
                :model-value="genreTags"
                :suggestions="library.authorNames.genres"
                :readonly="!canEdit"
                placeholder="Ajouter un genre…"
                @update:model-value="metadata.Genre = $event.join(', ')"
              />
            </div>
            <div class="meta-field">
              <label class="form-label">Étiquettes</label>
              <TagInput v-model="userTags" />
            </div>
            <div class="meta-field">
              <label class="form-label">Note personnelle</label>
              <StarRating v-model="userRating" />
            </div>

            <div class="meta-divider"></div>

            <div class="meta-field">
              <label class="form-label">Résumé</label>
              <textarea
                :value="metadata.Summary || ''"
                :readonly="!canEdit"
                class="form-control form-textarea" rows="6" placeholder="Résumé de l'album…"
                @input="metadata.Summary = $event.target.value"
              ></textarea>
            </div>

            <!-- Champs ComicInfo secondaires — masqués par défaut (voir EXTRA_FIELDS),
                 affichés seulement s'ils ont déjà une valeur ou ont été ajoutés à la main. -->
            <div v-for="f in visibleExtraFields" :key="f.key" class="meta-field">
              <label class="form-label">{{ f.label }}</label>
              <input
                :value="metadata[f.key] || ''"
                :readonly="!canEdit"
                type="text"
                @input="metadata[f.key] = $event.target.value"
                class="form-control" :class="{ readonly: !canEdit }"
              />
            </div>
            <div v-if="canEdit && hiddenExtraFields.length" class="add-field-wrap" ref="addFieldMenuRef">
              <button type="button" class="add-field-link" @click="showAddFieldMenu = !showAddFieldMenu">
                <SvgIcon name="square-plus" /> Ajouter un champ
              </button>
              <div v-if="showAddFieldMenu" class="add-field-menu">
                <button
                  v-for="f in hiddenExtraFields" :key="f.key" type="button"
                  class="add-field-menu-item" @click="addExtraField(f.key)"
                >{{ f.label }}</button>
              </div>
            </div>

            <div class="meta-divider"></div>

            <!-- Infos fichier — lecture seule -->
            <div v-if="fileInfo" class="file-info-card">
              <div class="file-info-line">
                <span class="file-info-label">Chemin :</span>
                <span class="file-info-path">{{ fileInfo.filepath }}</span>
              </div>
              <div class="file-info-line">
                <span class="file-info-label">Taille :</span>
                <span class="file-info-value">{{ fmtSize(fileInfo.file_size) }}</span>
              </div>
              <div class="file-info-line">
                <span class="file-info-label">Résolution :</span>
                <span class="file-info-value">{{ fileInfo.image_width && fileInfo.image_height ? `${fileInfo.image_width} × ${fileInfo.image_height} px` : '—' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button @click="cancel" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Sauvegarde…' : 'Sauvegarder' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Popup confirmation suppression -->
    <div v-if="confirmDelete" class="confirm-backdrop" @click.self="confirmDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer l'album ?</p>
        <p class="confirm-desc"><strong>{{ tome.title || tome.filename }}</strong> et son fichier seront supprimés définitivement.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteTome" :disabled="deleting">
            {{ deleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Scraper modal -->
    <ScraperModal
      v-if="showScraper"
      :series="metadata.Series"
      :number="metadata.Number"
      :series-id="isOneshot ? null : tome.series_id"
      :title="tome.title"
      :is-oneshot="isOneshot"
      @select="applyScraperResult"
      @close="showScraper = false"
    />
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
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
  max-width: 700px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-header-info {
  flex: 1;
  min-width: 0;
}

.modal-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.modal-subtitle { font-size: 0.76rem; color: var(--muted); margin-top: 2px; }

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 20px 16px;
}

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

/* Onglet Album — cartes par section (maquette), chacune pleine largeur. */
@media (max-width: 720px) {
  .meta-field-row-3 { grid-template-columns: 1fr !important; }
}

.form-section {
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; display: flex; flex-direction: column; gap: 12px;
}
.form-section-title { display: flex; align-items: center; gap: 12px; }
.form-section-name { font-size: 0.9rem; font-weight: 700; color: var(--text); }
.required { color: var(--vermilion); }

.meta-field-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; align-items: start; }
.meta-field-number { width: 90px; flex-shrink: 0; }

.meta-col { display: flex; flex-direction: column; gap: 11px; min-width: 0; }
.meta-field { display: flex; flex-direction: column; gap: 3px; }
.meta-field-row { display: flex; align-items: flex-end; gap: 10px; }
.meta-field-grow { flex: 1; min-width: 0; }
.meta-divider { height: 1px; background: var(--border); margin: 1px 0; }

/* Libellés et placeholders allégés — plus discrets que le style de formulaire par défaut de
   l'app, pour ne pas alourdir une popup déjà dense en champs. */
.meta-col .form-label { font-size: 0.72rem; font-weight: 500; color: var(--muted); margin-bottom: 3px; }
.meta-col .form-control::placeholder,
.meta-col .form-textarea::placeholder { color: var(--placeholder); opacity: 0.75; }

.form-textarea { resize: vertical; font-family: var(--font); line-height: 1.5; min-height: 110px; }

.oneshot-inline {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.8125rem; color: var(--text);
  cursor: pointer;
  /* même boîte verticale qu'un .form-control (padding 7px + bordure 1px) pour s'aligner
     pile avec le champ à côté */
  padding: 7px 0;
  border: 1px solid transparent;
  box-sizing: border-box;
  white-space: nowrap;
}
.oneshot-inline .toggle-checkbox { accent-color: var(--primary); flex-shrink: 0; }

.modal-warning {
  margin-bottom: 16px;
  font-size: 0.8125rem;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

/* Fiche Bedetheque — icône "Consulter" discrète dans le champ, visible au survol/focus
   uniquement (secondaire par rapport à "Récupérer", à côté). */
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

/* Bouton "Récupérer" — teinté vermillon (même palette que les badges TagInput) pour se
   détacher nettement du champ texte juste à côté. Sur la même ligne que le champ (gain de
   place) plutôt qu'en dessous — d'où le libellé raccourci. */
.btn-bedetheque {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  flex-shrink: 0; white-space: nowrap;
  padding: 0 14px; height: 34px; border-radius: var(--radius-sm); border: none; cursor: pointer;
  background: var(--vermilion-light); color: var(--vermilion);
  font-family: var(--font); font-size: 0.8125rem; font-weight: 600;
  transition: background 0.12s, color 0.12s;
}
.btn-bedetheque:hover { background: var(--vermilion); color: #fff; }

/* "Ajouter un champ" — lien discret plutôt qu'un bouton bordé. */
.add-field-wrap { position: relative; align-self: flex-start; }
.add-field-link {
  display: inline-flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: pointer; padding: 2px 0;
  color: var(--vermilion); font-weight: 600; font-size: 0.8125rem; font-family: var(--font);
}
.add-field-link:hover { text-decoration: underline; }
/* Ouvre vers le HAUT (comme les suggestions de TagInput) : le bouton peut se retrouver en
   milieu de colonne, un menu qui s'ouvrirait vers le bas risquerait d'être rogné par le
   "overflow-y: auto" de .modal-body. */
.add-field-menu {
  position: absolute; bottom: calc(100% + 4px); left: 0; z-index: 10;
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius-sm); box-shadow: var(--shadow-lg);
  min-width: 210px; max-height: 260px; overflow-y: auto;
}
.add-field-menu-item {
  display: block; width: 100%;
  background: none; border: none; cursor: pointer; text-align: left;
  padding: 8px 12px; font-size: 0.8125rem; font-family: var(--font); color: var(--text);
}
.add-field-menu-item:hover { background: var(--light); }

.file-info-card {
  padding: 10px 12px;
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  display: flex; flex-direction: column; gap: 6px;
}
.file-info-line {
  display: flex; gap: 10px; align-items: baseline;
}
.file-info-label {
  font-size: 0.75rem; color: var(--muted);
  min-width: 72px; flex-shrink: 0;
}
.file-info-value { font-size: 0.8rem; color: var(--text); }
.file-info-path { font-family: monospace; font-size: 0.7rem; color: var(--muted); overflow-wrap: break-word; word-break: break-word; }

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
