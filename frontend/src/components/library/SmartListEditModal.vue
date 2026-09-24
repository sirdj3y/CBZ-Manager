<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { smartListsApi } from '../../api/smartLists'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'
import AutocompleteInput from '../ui/AutocompleteInput.vue'
import { SOURCE_LABELS, OPERATOR_LABELS, groupsToFlat, flatToGroups } from '../../utils/smartListRules'

const props = defineProps({
  smartList: { type: Object, default: null }, // null = création, objet = édition
})
const emit = defineEmits(['close', 'saved'])
const notif = useNotificationStore()
const library = useLibraryStore()

const isEdit = computed(() => !!props.smartList)

const step = ref(1) // 1 = Informations, 2 = Filtres, 3 = Vérification
const STEPS = [
  { n: 1, label: 'Informations' },
  { n: 2, label: 'Filtres' },
  { n: 3, label: 'Vérification' },
]

const name = ref(props.smartList?.name || '')
const shared = ref(props.smartList?.shared || false)
const fieldsCatalog = ref([])
const loadingFields = ref(true)
const saving = ref(false)
const errorMsg = ref('')

// Liste plate — chaque condition (sauf la première) porte le connecteur qui la relie à la
// précédente ('AND' ou 'OR'), évalué strictement de gauche à droite, ET plus fort que OU
// (même convention que les smart playlists Plex/iTunes) : "A ET B OU C" = "(A ET B) OU C".
// Ça reste strictement équivalent au moteur de règles du backend (groupes en OU, conditions
// en ET dans un groupe) — voir groupsToFlat/flatToGroups, qui font l'aller-retour sans rien
// perdre : une suite de connecteurs 'AND' forme un groupe, un 'OR' démarre le suivant.
const conditions = ref([])

function fieldsForSource(source) {
  return fieldsCatalog.value.filter(f => f.source === source)
}
function fieldMeta(cond) {
  return fieldsCatalog.value.find(f => f.source === cond.source && f.field === cond.field)
}
function operatorsFor(cond) {
  return fieldMeta(cond)?.operators || []
}
function choicesFor(cond) {
  return fieldMeta(cond)?.choices || null
}
function typeFor(cond) {
  return fieldMeta(cond)?.type || 'text'
}
function inputType(cond) {
  const t = typeFor(cond)
  if (t === 'numeric') return 'number'
  if (t === 'date') return 'date'
  return 'text'
}
function needsValue(cond) {
  return cond.operator !== 'is_empty' && cond.operator !== 'is_not_empty'
}

// Pool commun scénaristes + dessinateurs (dédupliqué) — même logique que ContentToolbar/
// SeriesMetadataModal : un auteur polyvalent (ex. Peyo) apparaît dans les deux métiers.
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

// Suggestions des valeurs déjà utilisées dans la bibliothèque, pour les champs texte "à
// choix ouvert mais en pratique limité" (contrairement à Extension/Classification, des
// listes vraiment fermées déjà gérées via choicesFor) — évite de retaper à l'identique un
// genre/auteur/étiquette existant, sans empêcher d'en saisir un nouveau.
function suggestionsFor(cond) {
  if (cond.source === 'metadata' && cond.field === 'Genre') return library.authorNames.genres
  if (cond.source === 'metadata' && (cond.field === 'Writer' || cond.field === 'Penciller')) return authorPool.value
  if (cond.source === 'metadata' && cond.field === 'Publisher') return library.authorNames.publishers
  if (cond.source === 'file' && cond.field === 'tag') return library.authorNames.tags
  return null
}

function emptyCondition(connector) {
  const first = fieldsCatalog.value[0]
  const base = first
    ? { source: first.source, field: first.field, operator: first.operators[0], value: '', value2: '' }
    : { source: 'file', field: '', operator: 'contains', value: '', value2: '' }
  return { ...base, connector }
}

// Suggestions de départ (étape 1, création uniquement) — un clic remplace entièrement la
// condition (encore vide à ce stade) par ce point de départ ; l'étape 2 permet ensuite de
// l'affiner ou d'en ajouter d'autres. Pas de combinaison multi-badge : rester simple, "choisis
// un point de départ" plutôt qu'un mini-générateur de règles en soi.
const SUGGESTED_FILTERS = [
  { label: 'One-shot', source: 'file', field: 'is_oneshot', operator: 'is', value: 'true' },
  { label: 'Sans genre', source: 'metadata', field: 'Genre', operator: 'is_empty', value: '' },
  { label: 'Sans classification', source: 'series', field: 'classification', operator: 'is_empty', value: '' },
  { label: 'Ajouté récemment (30j)', source: 'file', field: 'created_at', operator: 'gt', value: null },
]
function applySuggestedFilter(preset) {
  let value = preset.value
  if (value === null) {
    const d = new Date()
    d.setDate(d.getDate() - 30)
    value = d.toISOString().slice(0, 10)
  }
  conditions.value = [{ source: preset.source, field: preset.field, operator: preset.operator, value, value2: '', connector: null }]
  // Saut direct à l'étape Filtres — sinon le clic ne produit aucun changement visible à
  // l'écran (la condition est bien préremplie, mais invisible tant qu'on est encore à
  // l'étape 1).
  step.value = 2
}


async function loadFields() {
  if (!library.authorNames.writers.length) library.fetchAuthors()
  loadingFields.value = true
  try {
    const { data } = await smartListsApi.fields()
    fieldsCatalog.value = data
  } finally {
    loadingFields.value = false
  }
  // La condition vide initiale dépend du catalogue (reprend son premier champ) — construite
  // seulement une fois celui-ci chargé. value/value2 normalisés à '' (jamais null) pour des
  // champs de formulaire contrôlés.
  const flat = groupsToFlat(props.smartList?.rules?.groups).map(c => ({ ...c, value: c.value ?? '', value2: c.value2 ?? '' }))
  conditions.value = flat.length ? flat : [emptyCondition(null)]
}
onMounted(loadFields)

// Échap pour fermer, comme les autres modales de l'app (voir SeriesMetadataModal.vue) — pas
// de raccourci Entrée ici : le formulaire est multi-étapes et Entrée en cours de saisie
// d'une valeur n'a pas de sens univoque (sauvegarder ? étape suivante ?).
function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

function onSourceChange(cond) {
  const first = fieldsForSource(cond.source)[0]
  cond.field = first ? first.field : ''
  cond.operator = first ? first.operators[0] : 'contains'
  cond.value = ''
  cond.value2 = ''
}
function onFieldChange(cond) {
  const ops = operatorsFor(cond)
  if (!ops.includes(cond.operator)) cond.operator = ops[0] || 'contains'
  cond.value = ''
  cond.value2 = ''
}
function onOperatorChange(cond) {
  if (!needsValue(cond)) cond.value = ''
  if (cond.operator !== 'between') cond.value2 = ''
}

function addCondition() { conditions.value.push(emptyCondition('AND')) }
function removeCondition(idx) {
  conditions.value.splice(idx, 1)
  if (conditions.value.length === 0) conditions.value.push(emptyCondition(null))
}

function goNext() {
  errorMsg.value = ''
  if (step.value === 1) {
    if (!name.value.trim()) { errorMsg.value = 'Le nom est requis'; return }
  }
  if (step.value === 2) {
    for (const c of conditions.value) {
      if (!needsValue(c)) continue
      if (c.value === '' || c.value === null) { errorMsg.value = 'Chaque condition doit avoir une valeur (ou un opérateur "est vide" / "n\'est pas vide")'; return }
      if (c.operator === 'between' && (c.value2 === '' || c.value2 === null)) { errorMsg.value = "L'opérateur \"entre\" demande une valeur de fin"; return }
    }
  }
  step.value += 1
}
function goPrev() {
  errorMsg.value = ''
  step.value -= 1
}

async function save() {
  errorMsg.value = ''
  const trimmedName = name.value.trim()
  const rules = {
    groups: flatToGroups(conditions.value).map(g => ({
      conditions: g.conditions.map(c => ({
        source: c.source, field: c.field, operator: c.operator,
        value: c.value === '' ? null : String(c.value),
        value2: c.value2 === '' ? null : String(c.value2),
      })),
    })),
  }
  saving.value = true
  try {
    let result
    if (isEdit.value) {
      ;({ data: result } = await smartListsApi.update(props.smartList.id, { name: trimmedName, shared: shared.value, rules }))
      notif.success('Liste mise à jour')
    } else {
      ;({ data: result } = await smartListsApi.create({ name: trimmedName, shared: shared.value, rules }))
      notif.success('Liste créée')
    }
    // isCreate permet à l'appelant (AppLayout) de naviguer directement sur la nouvelle liste
    // — inutile en édition, on reste déjà sur sa page le cas échéant.
    emit('saved', { list: result, isCreate: !isEdit.value })
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || "Erreur lors de l'enregistrement"
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click="$emit('close')" />

    <div class="modal-wrap">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">{{ isEdit ? 'Modifier la liste' : 'Nouvelle Smart list' }}</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <!-- Stepper -->
        <div class="stepper">
          <template v-for="(s, i) in STEPS" :key="s.n">
            <div v-if="i > 0" class="stepper-line" :class="{ 'stepper-line-done': step > s.n - 1 }" />
            <button
              type="button"
              class="stepper-step"
              :class="{ 'stepper-step-active': step === s.n, 'stepper-step-done': step > s.n }"
              :disabled="s.n > step"
              @click="s.n < step && (step = s.n)"
            >
              <span class="stepper-circle">{{ s.n }}</span>
              <span class="stepper-label">{{ s.label }}</span>
            </button>
          </template>
        </div>

        <div class="modal-body">
          <div v-if="loadingFields" class="state-pulse">Chargement…</div>
          <template v-else>
            <!-- Étape 1 : Informations -->
            <template v-if="step === 1">
              <div class="field">
                <label class="form-label">Nom</label>
                <input v-model="name" type="text" class="form-control" placeholder="ex: Mangas terminés" autofocus />
              </div>
              <label class="toggle-label">
                <input type="checkbox" v-model="shared" class="toggle-checkbox" />
                <span>Visible pour tous les utilisateurs</span>
              </label>
              <div v-if="!isEdit" class="field">
                <label class="form-label">Suggestions</label>
                <div class="suggestion-badges">
                  <button v-for="s in SUGGESTED_FILTERS" :key="s.label" type="button" class="suggestion-badge" @click="applySuggestedFilter(s)">{{ s.label }}</button>
                </div>
              </div>
            </template>

            <!-- Étape 2 : Filtres -->
            <template v-if="step === 2">
              <p class="step-hint">ET est évalué avant OU (de gauche à droite) — comme la plupart des lecteurs à listes intelligentes.</p>
              <div class="rules">
                <template v-for="(cond, idx) in conditions" :key="idx">
                  <div v-if="idx > 0" class="connector-toggle">
                    <button type="button" :class="['connector-btn', { 'connector-btn-active': cond.connector === 'AND' }]" @click="cond.connector = 'AND'">ET</button>
                    <button type="button" :class="['connector-btn', { 'connector-btn-active': cond.connector === 'OR' }]" @click="cond.connector = 'OR'">OU</button>
                  </div>
                  <div class="rule-row">
                    <select v-model="cond.source" class="form-control rule-select-source" @change="onSourceChange(cond)">
                      <option v-for="s in ['file','metadata','series']" :key="s" :value="s">{{ SOURCE_LABELS[s] }}</option>
                    </select>
                    <select v-model="cond.field" class="form-control rule-select-field" @change="onFieldChange(cond)">
                      <option v-for="f in fieldsForSource(cond.source)" :key="f.field" :value="f.field">{{ f.label }}</option>
                    </select>
                    <select v-model="cond.operator" class="form-control rule-select-operator" @change="onOperatorChange(cond)">
                      <option v-for="op in operatorsFor(cond)" :key="op" :value="op">{{ OPERATOR_LABELS[op] || op }}</option>
                    </select>
                    <template v-if="needsValue(cond)">
                      <select v-if="typeFor(cond) === 'boolean'" v-model="cond.value" class="form-control rule-value">
                        <option value="true">Oui</option>
                        <option value="false">Non</option>
                      </select>
                      <select v-else-if="choicesFor(cond)" v-model="cond.value" class="form-control rule-value">
                        <option value="">—</option>
                        <option v-for="c in choicesFor(cond)" :key="c" :value="c">{{ c }}</option>
                      </select>
                      <AutocompleteInput
                        v-else-if="suggestionsFor(cond)"
                        v-model="cond.value"
                        :suggestions="suggestionsFor(cond)"
                        show-all-on-focus
                        class="rule-value"
                      />
                      <input v-else v-model="cond.value" :type="inputType(cond)" class="form-control rule-value" :step="typeFor(cond) === 'numeric' ? 'any' : undefined" />
                      <template v-if="cond.operator === 'between'">
                        <span class="rule-between-and">et</span>
                        <input v-model="cond.value2" :type="inputType(cond)" class="form-control rule-value" :step="typeFor(cond) === 'numeric' ? 'any' : undefined" />
                      </template>
                    </template>
                    <button type="button" class="rule-remove" title="Retirer cette condition" @click="removeCondition(idx)">✕</button>
                  </div>
                </template>
                <button type="button" class="btn btn-ghost btn-sm rule-add-cond" @click="addCondition">+ condition</button>
              </div>
            </template>

            <!-- Étape 3 : Vérification -->
            <template v-if="step === 3">
              <div class="review-block">
                <p class="review-label">Nom</p>
                <p class="review-value">{{ name }}</p>
              </div>
              <div class="review-block">
                <p class="review-label">Visibilité</p>
                <p class="review-value">{{ shared ? 'Visible pour tous les utilisateurs' : 'Privée' }}</p>
              </div>
              <div class="review-block">
                <p class="review-label">Règles</p>
                <div class="review-group">
                  <p v-for="(cond, idx) in conditions" :key="idx" class="review-cond">
                    <span v-if="idx > 0" :class="['review-connector', cond.connector === 'OR' ? 'review-connector-or' : 'review-connector-and']">{{ cond.connector === 'OR' ? 'OU' : 'ET' }}</span>
                    {{ SOURCE_LABELS[cond.source] }} · {{ fieldMeta(cond)?.label || cond.field }}
                    {{ OPERATOR_LABELS[cond.operator] || cond.operator }}
                    <template v-if="needsValue(cond)">« {{ cond.value }} »<template v-if="cond.operator === 'between'"> et « {{ cond.value2 }} »</template></template>
                  </p>
                </div>
              </div>
            </template>

            <p v-if="errorMsg" class="rule-error">{{ errorMsg }}</p>
          </template>
        </div>

        <div class="modal-footer">
          <button v-if="step > 1" @click="goPrev" class="btn btn-ghost btn-sm">← Précédent</button>
          <button v-else @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <div style="flex:1"></div>
          <button v-if="step < 3" @click="goNext" :disabled="loadingFields" class="btn btn-primary btn-sm">Suivant →</button>
          <button v-else @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Enregistrement…' : (isEdit ? 'Enregistrer' : 'Créer') }}
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
  position: fixed; inset: 0; z-index: 201;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; pointer-events: none;
}
.modal-box {
  pointer-events: auto;
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%; max-width: 680px; max-height: 90vh;
  display: flex; flex-direction: column;
}
.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header-info { flex: 1; min-width: 0; }
.modal-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.modal-body {
  flex: 1; overflow-y: auto;
  padding: 16px; display: flex; flex-direction: column; gap: 14px;
}
.modal-footer {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

/* Stepper */
.stepper {
  display: flex; align-items: center; justify-content: center;
  padding: 14px 16px 0; flex-shrink: 0; gap: 4px;
}
.stepper-step {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: not-allowed; padding: 4px 6px;
  border-radius: var(--radius-sm);
}
.stepper-step:disabled { cursor: not-allowed; }
.stepper-step-done { cursor: pointer; }
.stepper-circle {
  width: 22px; height: 22px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.72rem; font-weight: 700;
  border: 1.5px solid var(--border); color: var(--muted);
  flex-shrink: 0;
}
.stepper-label { font-size: 0.78rem; color: var(--muted); white-space: nowrap; }
.stepper-step-active .stepper-circle { border-color: var(--primary); color: var(--primary); }
.stepper-step-active .stepper-label { color: var(--text); font-weight: 600; }
.stepper-step-done .stepper-circle { border-color: var(--primary); background: var(--primary); color: #fff; }
.stepper-step-done .stepper-label { color: var(--text); }
.stepper-line { width: 28px; height: 1.5px; background: var(--border); flex-shrink: 0; }
.stepper-line-done { background: var(--primary); }

.step-hint { font-size: 0.8rem; color: var(--muted); margin: 0; }

.field { display: flex; flex-direction: column; gap: 4px; }
.toggle-label { display: flex; align-items: center; gap: 8px; font-size: 0.8125rem; color: var(--text); cursor: pointer; }
.toggle-checkbox { accent-color: var(--primary); flex-shrink: 0; }

.suggestion-badges { display: flex; flex-wrap: wrap; gap: 6px; }
.suggestion-badge {
  padding: 4px 12px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--light); color: var(--text);
  font-size: 0.78rem; font-family: var(--font); cursor: pointer;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.suggestion-badge:hover { background: var(--primary-light); border-color: var(--primary); color: var(--primary); }

.rules { display: flex; flex-direction: column; gap: 8px; }

/* Connecteur ET/OU entre deux lignes — les deux boutons ont exactement la même présentation,
   seul l'état actif (couleur pleine) distingue lequel s'applique. Même principe que les
   boutons de format (CBZ/CBR/PDF) de ContentToolbar.vue. */
.connector-toggle {
  align-self: center;
  display: flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden;
}
.connector-btn {
  padding: 2px 14px;
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; font-family: var(--font);
  border: none; background: var(--surface); color: var(--muted); cursor: pointer;
}
.connector-btn:first-child { border-right: 1px solid var(--border); }
.connector-btn-active { background: var(--primary); color: #fff; }

/* .form-control (global) met appearance:none sans fournir sa propre flèche — sans ceci, les
   select Fichier/Titre/est/... de cette étape ne montrent aucun indice visuel qu'ils sont
   des menus déroulants (même flèche que .sort-select dans ContentToolbar.vue). */
.rule-row select.form-control {
  padding-right: 26px;
  background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23757575'/%3E%3C/svg%3E") no-repeat right 9px center;
  cursor: pointer;
}

.rule-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rule-select-source { flex: 0 0 108px; }
.rule-select-field { flex: 1 1 150px; min-width: 130px; }
.rule-select-operator { flex: 0 0 150px; }
.rule-value { flex: 1 1 130px; min-width: 100px; }
.rule-between-and { font-size: 0.78rem; color: var(--muted); flex-shrink: 0; }
.rule-remove {
  flex-shrink: 0; width: 24px; height: 24px;
  border: none; background: none; color: var(--muted); cursor: pointer;
  border-radius: var(--radius-sm); font-size: 0.78rem;
}
.rule-remove:hover { background: var(--danger-bg-light); color: var(--danger); }
.rule-add-cond { align-self: flex-start; }

.rule-error { font-size: 0.8rem; color: var(--danger); }

.review-block { display: flex; flex-direction: column; gap: 4px; }
.review-label { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.review-value { font-size: 0.875rem; color: var(--text); }
.review-group {
  padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--light);
  display: flex; flex-direction: column; gap: 4px;
}
.review-cond { font-size: 0.8rem; color: var(--text); }
.review-connector {
  display: inline-block; font-weight: 700; font-size: 0.65rem; letter-spacing: 0.05em;
  padding: 1px 7px; border-radius: 999px; margin-right: 6px;
}
.review-connector-and { background: color-mix(in srgb, var(--light), var(--border)); color: var(--text); }
.review-connector-or { background: var(--primary-light); color: var(--primary); }

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }
</style>
