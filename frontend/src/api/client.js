import axios from 'axios'

const client = axios.create({
  baseURL: '',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Session expirée/invalide ailleurs qu'au login lui-même (dont l'appelant gère l'échec
// pour afficher un message dans le formulaire) → redirection dure vers /login, qui
// réinitialise proprement tout l'état Pinia au passage.
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err.config?.url || ''
    const isAuthEndpoint = url.includes('/api/auth/')
    if (err.response?.status === 401 && !isAuthEndpoint && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
