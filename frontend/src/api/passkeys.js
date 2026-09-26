import client from './client'

export const passkeysApi = {
  status: () => client.get('/api/auth/passkeys/status'),
  list: () => client.get('/api/auth/passkeys'),
  registerOptions: () => client.post('/api/auth/passkeys/register/options'),
  registerVerify: (payload) => client.post('/api/auth/passkeys/register/verify', payload),
  remove: (id) => client.delete(`/api/auth/passkeys/${id}`),
  loginOptions: () => client.post('/api/auth/passkeys/login/options'),
  loginVerify: (payload) => client.post('/api/auth/passkeys/login/verify', payload),
}
