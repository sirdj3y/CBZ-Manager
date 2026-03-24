<script setup>
import { useNotificationStore } from '../../stores/notifications'
const notif = useNotificationStore()

const icons = { success: '✓', error: '✕', info: 'ℹ' }
</script>

<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="fade">
        <div
          v-for="n in notif.items"
          :key="n.id"
          :class="['toast', `toast-${n.type}`]"
        >
          <span class="toast-icon">{{ icons[n.type] }}</span>
          <span class="toast-message">{{ n.message }}</span>
          <button class="toast-close" @click="notif.remove(n.id)">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: var(--radius);
  border: 1px solid transparent;
  box-shadow: var(--shadow-lg);
  font-size: 0.875rem;
  min-width: 260px;
  max-width: 380px;
  pointer-events: auto;
  background: var(--surface);
}

.toast-success {
  background-color: var(--success-bg);
  border-color: var(--success-border);
  color: var(--success-text);
}
.toast-error {
  background-color: var(--danger-bg);
  border-color: var(--danger-border);
  color: var(--danger-text);
}
.toast-info {
  background-color: var(--surface);
  border-color: var(--border);
  color: var(--text);
}

.toast-icon {
  font-weight: 700;
  flex-shrink: 0;
}

.toast-message {
  flex: 1;
}

.toast-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  opacity: 0.5;
  padding: 0 2px;
  color: inherit;
  transition: opacity 0.15s;
  flex-shrink: 0;
}
.toast-close:hover {
  opacity: 1;
}
</style>
