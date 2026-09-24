<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import client from '../../api/client'

// labels : { tomeId: nom à afficher } — l'id de tome seul (clé technique interne, sans
// rapport avec le numéro de tome affiché ailleurs dans l'app) prêtait à confusion affiché
// tel quel ("Tome 89"), pris pour un numéro de volume délirant.
const props = defineProps({
  jobId: { type: Number, required: true },
  labels: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['done'])

const tomes = ref({})
const overall = ref('running')
const cancelling = ref(false)
let source = null

onMounted(() => {
  source = new EventSource(`/api/convert/${props.jobId}/stream`, { withCredentials: true })
  source.onmessage = (e) => {
    const data = JSON.parse(e.data)
    tomes.value = data.tomes
    overall.value = data.status
    // "error" est désormais un statut terminal distinct de "done" (voir routers/converter.py
    // ::convert_stream) — un lot avec au moins un tome en erreur ne doit plus s'afficher
    // comme un succès complet, mais reste terminal : le flux se ferme dans les deux cas.
    if (data.status === 'done' || data.status === 'error') {
      source.close()
      setTimeout(() => emit('done'), 1500)
    }
  }
  source.onerror = () => source.close()
})

onUnmounted(() => source?.close())

function pct(t) {
  if (!t.total) return 0
  return Math.round((t.progress / t.total) * 100)
}

async function cancel() {
  cancelling.value = true
  try {
    await client.delete(`/api/convert/${props.jobId}`)
  } catch { /* déjà terminé */ }
}

const statusLabel = { pending: 'En attente', running: 'En cours…', done: '✓ Terminé', error: '✕ Erreur' }
</script>

<template>
  <div class="progress-body">
    <div v-for="(t, tomeId) in tomes" :key="tomeId" class="progress-item">
      <div class="progress-item-header">
        <span class="progress-tome-label">{{ labels[tomeId] || 'Fichier' }}</span>
        <span :class="['progress-status', `progress-status-${t.status}`]">{{ statusLabel[t.status] }}</span>
      </div>
      <div class="progress-track">
        <div
          :class="['progress-fill', { 'progress-fill-error': t.status === 'error' }]"
          :style="{ width: `${pct(t)}%` }"
        />
      </div>
    </div>

    <p :class="['progress-overall', { 'progress-overall-done': overall === 'done', 'progress-overall-error': overall === 'error' }]">
      {{ overall === 'done' ? '✓ Conversion terminée !' : overall === 'error' ? '✕ Terminée avec des erreurs (voir le détail ci-dessus)' : 'Conversion en cours…' }}
    </p>

    <div v-if="overall === 'running'" class="progress-footer">
      <button
        class="btn btn-danger btn-sm"
        :disabled="cancelling"
        @click="cancel"
      >
        {{ cancelling ? 'Annulation…' : 'Annuler la conversion' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.progress-body {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.progress-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8125rem;
}

.progress-tome-label {
  color: var(--muted);
}

.progress-status {
  font-weight: 500;
}
.progress-status-pending { color: var(--muted); }
.progress-status-running { color: var(--primary); }
.progress-status-done    { color: var(--success); }
.progress-status-error   { color: var(--danger); }

.progress-track {
  height: 6px;
  background-color: var(--light);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: var(--primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}
.progress-fill-error {
  background-color: var(--danger);
}

.progress-overall {
  text-align: center;
  font-size: 0.875rem;
  color: var(--muted);
  padding-top: 4px;
}
.progress-overall-done {
  color: var(--success);
  font-weight: 600;
}
.progress-overall-error {
  color: var(--danger);
  font-weight: 600;
}

.progress-footer {
  display: flex;
  justify-content: center;
  padding-top: 4px;
}
.btn-danger {
  background: var(--danger); color: #fff; border: none;
}
.btn-danger:hover:not(:disabled) { opacity: 0.88; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
