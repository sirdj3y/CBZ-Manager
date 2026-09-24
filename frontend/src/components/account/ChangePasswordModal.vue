<script setup>
import { ref } from 'vue'
import { authApi } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import { useNotificationStore } from '../../stores/notifications'

const auth = useAuthStore()
const notif = useNotificationStore()

const form = ref({ current_password: '', new_password: '', confirm_password: '' })
const saving = ref(false)

function close() {
  auth.changePasswordOpen = false
  form.value = { current_password: '', new_password: '', confirm_password: '' }
}

async function save() {
  if (!form.value.current_password) {
    notif.error('Mot de passe actuel requis')
    return
  }
  if (form.value.new_password.length < 8) {
    notif.error('Le nouveau mot de passe doit faire au moins 8 caractères')
    return
  }
  if (form.value.new_password !== form.value.confirm_password) {
    notif.error('Les deux mots de passe ne correspondent pas')
    return
  }
  if (form.value.new_password === form.value.current_password) {
    notif.error('Le nouveau mot de passe doit être différent de l\'actuel')
    return
  }
  saving.value = true
  try {
    const { data } = await authApi.updateCredentials({
      current_password: form.value.current_password,
      new_password: form.value.new_password,
    })
    auth.applyStatus(data)
    notif.success('Mot de passe mis à jour')
    close()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la mise à jour')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click="close" />
    <div class="modal-wrap">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">Changer le mot de passe</p>
          </div>
          <button @click="close" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Mot de passe actuel</label>
            <input v-model="form.current_password" type="password" class="form-control" autocomplete="current-password" autofocus />
          </div>
          <div class="form-group">
            <label class="form-label">Nouveau mot de passe</label>
            <input v-model="form.new_password" type="password" class="form-control" placeholder="8 caractères minimum" autocomplete="new-password" @keyup.enter="save" />
          </div>
          <div class="form-group">
            <label class="form-label">Confirmer</label>
            <input v-model="form.confirm_password" type="password" class="form-control" autocomplete="new-password" @keyup.enter="save" />
          </div>
          <p class="form-hint" style="margin:0">
            Changer le mot de passe déconnecte automatiquement toute autre session ouverte ailleurs.
          </p>
        </div>
        <div class="modal-footer">
          <div class="modal-footer-spacer" />
          <button class="btn btn-ghost btn-sm" @click="close">Annuler</button>
          <button class="btn btn-primary btn-sm" :disabled="saving" @click="save">
            {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Squelette de modale — même pattern que RenameModal.vue / SettingsUsersView.vue. */
.modal-backdrop { position: fixed; inset: 0; z-index: 200; background: var(--overlay-bg); }
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
  width: 100%; max-width: 400px;
  display: flex; flex-direction: column;
}
.modal-header { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.modal-header-info { flex: 1; min-width: 0; }
.modal-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.modal-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; font-size: 0.85rem; color: var(--text); }
.modal-footer {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px;
  border-top: 1px solid var(--border); background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}
.modal-footer-spacer { flex: 1; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-hint { font-size: 0.8rem; color: var(--muted); }
</style>
