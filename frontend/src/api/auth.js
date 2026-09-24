import client from './client'

export const authApi = {
  me: () => client.get('/api/auth/me'),
  login: (username, password) => client.post('/api/auth/login', { username, password }),
  logout: () => client.post('/api/auth/logout'),
  updateCredentials: (payload) => client.put('/api/auth/credentials', payload),
  uploadAvatar: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/api/auth/avatar', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  removeAvatar: () => client.delete('/api/auth/avatar'),
  avatarPresets: () => client.get('/api/auth/avatar-presets'),
  applyAvatarPreset: (n) => client.post('/api/auth/avatar-preset', { preset: n }),
}
