import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'
export const API_ORIGIN = API_BASE.replace(/\/api\/?$/, '')

const apiClient = axios.create({ baseURL: API_BASE, timeout: 600000 })
export default apiClient
