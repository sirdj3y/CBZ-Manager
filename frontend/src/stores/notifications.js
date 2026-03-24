import { defineStore } from 'pinia'
import { ref } from 'vue'

let _id = 0

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref([])

  function push(message, type = 'info', duration = 3500) {
    const id = ++_id
    items.value.push({ id, message, type })
    setTimeout(() => remove(id), duration)
  }

  function remove(id) {
    items.value = items.value.filter(n => n.id !== id)
  }

  const success = (msg) => push(msg, 'success')
  const error = (msg) => push(msg, 'error', 5000)
  const info = (msg) => push(msg, 'info')

  return { items, push, remove, success, error, info }
})
