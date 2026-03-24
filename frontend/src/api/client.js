import axios from 'axios'

const client = axios.create({
  baseURL: '',
  withCredentials: false,
  headers: { 'Content-Type': 'application/json' },
})

export default client
