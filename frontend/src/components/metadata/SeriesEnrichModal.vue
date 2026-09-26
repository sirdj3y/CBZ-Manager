<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { libraryApi } from '../../api/library'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'
import AutocompleteInput from '../ui/AutocompleteInput.vue'
import AppDialog from '../ui/AppDialog.vue'

const props = defineProps({
  series: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const notif = useNotificationStore()
const library = useLibraryStore()

// Même pool que le reste de l'app (fiche album/série) : Scénariste et Dessinateur partagent
// les mêmes suggestions (un auteur polyvalent apparaît dans les deux).
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})
function suggestionsFor(key) {
  if (key === 'Writer' || key === 'Penciller') return authorPool.value
  if (key === 'Publisher') return library.authorNames.publishers
  return []
}

// Ordre demandé : Numéro, Titre, Année, Dessinateur, Scénariste, Éditeur. Titre est rendu à
// part dans le template (colonne pleine largeur, comme Album avant elle) — les 4 autres
// partagent une largeur fixe via la boucle générique ci-dessous.
const COLUMNS = [
  { key: 'Year', label: 'Année' },
  { key: 'Penciller', label: 'Dessinateur' },
  { key: 'Writer', label: 'Scénariste' },
  { key: 'Publisher', label: 'Éditeur' },
  { key: 'ISBN', label: 'ISBN' },
  { key: 'Web', label: 'Fiche Bedetheque' },
]
// Champs texte simple (pas d'autocomplétion auteurs/éditeur) — même liste que le rendu
// conditionnel du template ci-dessous.
const PLAIN_FIELDS = new Set(['Year', 'ISBN', 'Web'])
// Tous les champs suivis, Titre compris — pour tout ce qui doit les parcourir sans se
// soucier de sa mise en forme particulière (compteur de changements, application).
const ALL_FIELDS = ['Title', ...COLUMNS.map(c => c.key)]

const loading = ref(true)
const loadError = ref('')
const files = ref([]) // [{ id, name, number, fields: [{ field, field_label, current, scraped }] }]
const draft = reactive({}) // "tomeId:field" -> texte actuellement dans la cellule éditable
const filterText = ref('')
const applying = ref(false)

function dkey(fileId, field) { return `${fileId}:${field}` }
function stem(filename) { return filename.replace(/\.[^.]+$/, '') }
function displayTitle(file) { return file.title || stem(file.name) }
function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  return /^\d+$/.test(s) ? s.padStart(2, '0') : s
}
function fieldOf(file, key) { return file.fields.find(f => f.field === key) }

const filteredFiles = computed(() => {
  const q = filterText.value.trim().toLowerCase()
  if (!q) return files.value
  return files.value.filter(f => displayTitle(f).toLowerCase().includes(q))
})

// Valeur de référence d'une cellule = ce qu'il y avait avant ouverture de la popup (le champ
// existant, sinon vide) — sert à savoir si l'utilisateur a réellement modifié quelque chose,
// que la cellule ait démarré vide (ajout) ou déjà renseignée (correction).
function originalValue(file, key) {
  return fieldOf(file, key)?.current || ''
}
function isChanged(file, key) {
  const k = dkey(file.id, key)
  const val = (draft[k] || '').trim()
  // Un champ vidé par l'utilisateur est ignoré côté backend (voir apply()/library.py) —
  // ne pas le compter/surligner comme "à appliquer", sinon le compteur et le surlignage
  // annoncent un changement qui ne sera en réalité jamais écrit.
  if (!val) return false
  return val !== originalValue(file, key).trim()
}

const changedCount = computed(() =>
  files.value.reduce((n, f) => n + ALL_FIELDS.filter(key => isChanged(f, key)).length, 0)
)

function resetDraft() {
  for (const k of Object.keys(draft)) delete draft[k]
  files.value.forEach(f => f.fields.forEach(c => {
    draft[dkey(f.id, c.field)] = c.current || c.scraped || ''
  }))
}

function useSuggestion(file, key) {
  draft[dkey(file.id, key)] = fieldOf(file, key).scraped
}

// Reprend, pour chaque cellule où Bedetheque propose une valeur différente de celle
// actuellement affichée (ajout comme correction), cette valeur en un seul clic.
function acceptAllSuggestions() {
  files.value.forEach(f => {
    ALL_FIELDS.forEach(key => {
      const field = fieldOf(f, key)
      if (field?.scraped) draft[dkey(f.id, key)] = field.scraped
    })
  })
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await libraryApi.previewSeriesEnrich(props.series.id)
    files.value = data.files
    resetDraft()
  } catch (e) {
    loadError.value = e.response?.data?.detail || "Impossible de charger l'aperçu."
  } finally {
    loading.value = false
  }
}

async function apply() {
  const updates = []
  files.value.forEach(f => {
    ALL_FIELDS.forEach(key => {
      const val = (draft[dkey(f.id, key)] || '').trim()
      if (val && isChanged(f, key)) {
        updates.push({ tome_id: f.id, field: key, value: val })
      }
    })
  })
  if (!updates.length) return
  applying.value = true
  try {
    const { data } = await libraryApi.applySeriesEnrich(props.series.id, updates)
    if (data.errors) notif.error(`${data.errors} erreur(s) pendant l'application`)
    else notif.success(`${data.ok} album(s) mis à jour`)
    emit('saved')
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'application")
  } finally {
    applying.value = false
  }
}

onMounted(() => {
  if (!library.authorNames.writers.length) library.fetchAuthors()
  load()
})

</script>

<template>
  <AppDialog title="Compléter depuis Bedetheque.com" @close="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <div class="modal-header-info">
          <p class="modal-title">Compléter depuis Bedetheque.com</p>
          <p class="modal-subtitle">{{ series.name }}</p>
        </div>
        <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
      </div>

      <div v-if="loading" class="state-box"><span class="state-pulse">Analyse…</span></div>
      <div v-else-if="loadError" class="state-box"><span class="state-text">{{ loadError }}</span></div>
      <div v-else-if="!files.length" class="state-box">
        <span class="state-text">Aucun album possédé ne correspond à un album trouvé sur Bedetheque.</span>
      </div>
      <template v-else>
        <div class="toolbar">
          <button class="btn btn-secondary btn-sm" @click="acceptAllSuggestions">Accepter toutes les modifications</button>
          <input v-model="filterText" type="search" class="form-control filter-input" placeholder="Filtrer par titre…" />
        </div>

        <div class="modal-body">
          <div class="table-scroll">
            <table class="enrich-table">
              <thead>
                <tr>
                  <th class="col-num">N°</th>
                  <th class="col-title">Titre</th>
                  <th v-for="col in COLUMNS" :key="col.key" class="col-field">{{ col.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="file in filteredFiles" :key="file.id">
                  <td class="col-num">{{ fmtNumber(file.number) }}</td>
                  <td class="col-title">
                    <input
                      v-model="draft[dkey(file.id, 'Title')]"
                      type="text"
                      :placeholder="stem(file.name)"
                      :class="['cell-input', { 'cell-input-fill': isChanged(file, 'Title') }]"
                    />
                    <button
                      v-if="fieldOf(file, 'Title')?.scraped && fieldOf(file, 'Title').scraped !== draft[dkey(file.id, 'Title')]"
                      class="cell-suggest"
                      title="Reprendre cette valeur"
                      @click="useSuggestion(file, 'Title')"
                    >→ {{ fieldOf(file, 'Title').scraped }}</button>
                  </td>
                  <td v-for="col in COLUMNS" :key="col.key" class="col-field">
                    <input
                      v-if="PLAIN_FIELDS.has(col.key)"
                      v-model="draft[dkey(file.id, col.key)]"
                      type="text"
                      :class="['cell-input', { 'cell-input-fill': isChanged(file, col.key) }]"
                    />
                    <div v-else :class="['cell-autocomplete', { 'cell-autocomplete-fill': isChanged(file, col.key) }]">
                      <AutocompleteInput
                        v-model="draft[dkey(file.id, col.key)]"
                        :suggestions="suggestionsFor(col.key)"
                      />
                    </div>
                    <button
                      v-if="fieldOf(file, col.key)?.scraped && fieldOf(file, col.key).scraped !== draft[dkey(file.id, col.key)]"
                      class="cell-suggest"
                      title="Reprendre cette valeur"
                      @click="useSuggestion(file, col.key)"
                    >→ {{ fieldOf(file, col.key).scraped }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <div class="modal-footer">
        <span v-if="files.length" class="selection-count">{{ changedCount }} champ{{ changedCount > 1 ? 's' : '' }} à appliquer</span>
        <div class="footer-spacer" />
        <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
        <button
          v-if="files.length"
          @click="apply"
          :disabled="applying || !changedCount"
          class="btn btn-primary btn-sm"
        >{{ applying ? 'Application…' : 'Appliquer' }}</button>
      </div>
    </div>
  </AppDialog>
</template>

<style scoped>
.modal-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  width: 100%; max-width: 920px; max-height: 85vh;
  display: flex; flex-direction: column;
}
.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header-info { flex: 1; min-width: 0; }
.modal-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.modal-subtitle { font-size: 0.75rem; color: var(--muted); margin-top: 2px; }

.toolbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.modal-hint { font-size: 0.76rem; color: var(--muted); margin: 0; }
.filter-input { flex: 1; min-width: 140px; max-width: 220px; margin-left: auto; padding: 5px 10px; font-size: 0.8125rem; }

.modal-body { flex: 1; overflow-y: auto; padding: 0; }
.table-scroll { overflow-x: auto; }

/* table-layout: fixed + largeurs explicites par colonne — sans ça, max-width est ignoré par
   les navigateurs en layout "auto" et le texte du titre déborde sur les colonnes voisines
   au lieu de s'arrêter à sa colonne. */
.enrich-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.82rem; }
.enrich-table th {
  position: sticky; top: 0; z-index: 1;
  text-align: left; font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--muted);
  background: var(--light);
  padding: 8px 12px; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.enrich-table td {
  padding: 6px 12px; border-bottom: 1px solid var(--border);
  vertical-align: middle; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.enrich-table tbody tr:last-child td { border-bottom: none; }
.col-num { width: 48px; text-align: center; color: var(--muted); font-variant-numeric: tabular-nums; }
.col-title {
  width: auto; /* seule colonne sans largeur fixe : récupère tout l'espace restant */
  white-space: normal; overflow-wrap: break-word; overflow: visible; text-overflow: clip;
  vertical-align: top; padding-top: 8px;
  font-weight: 500; color: var(--text);
}
.col-field { width: 150px; white-space: normal; overflow: visible; text-overflow: clip; vertical-align: top; padding-top: 8px; }

/* Neutre par défaut (champ déjà renseigné, éditable pour corriger) — vert seulement quand
   la cellule diffère de sa valeur d'origine (ajout depuis Bedetheque ou correction). */
.cell-input {
  width: 100%; min-width: 110px;
  padding: 4px 6px; font-size: 0.82rem; font-family: var(--font);
  color: var(--text); font-weight: 400;
  background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.cell-input-fill {
  color: var(--success-text, var(--success)); font-weight: 600;
  background: var(--success-bg-light, var(--success-bg));
  border-color: transparent;
}
.cell-input:focus {
  outline: none; background: var(--surface);
  border-color: var(--primary-focus-border); box-shadow: 0 0 0 2px var(--primary-focus);
}

.cell-suggest {
  display: block; margin-top: 3px;
  background: none; border: none; padding: 0; cursor: pointer;
  font-size: 0.7rem; font-family: var(--font); color: var(--vermilion);
  text-align: left; white-space: normal;
}
.cell-suggest:hover { text-decoration: underline; }

.cell-autocomplete { min-width: 110px; }
.cell-autocomplete :deep(.form-control) {
  width: 100%;
  padding: 4px 6px; font-size: 0.82rem; font-family: var(--font);
  color: var(--text); font-weight: 400;
  background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.cell-autocomplete-fill :deep(.form-control) {
  color: var(--success-text, var(--success)); font-weight: 600;
  background: var(--success-bg-light, var(--success-bg));
  border-color: transparent;
}
.cell-autocomplete :deep(.form-control:focus) {
  outline: none; background: var(--surface);
  border-color: var(--primary-focus-border); box-shadow: 0 0 0 2px var(--primary-focus);
}

.modal-footer {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}
.selection-count { font-size: 0.8rem; color: var(--muted); }
.footer-spacer { flex: 1; }

.state-box { display: flex; align-items: center; justify-content: center; min-height: 100px; text-align: center; padding: 24px; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }
.state-text { font-size: 0.85rem; color: var(--muted); }
</style>
