import axios from 'axios'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
export const API_ORIGIN = API_BASE.replace(/\/api\/?$/, '')

const apiClient = axios.create({ baseURL: API_BASE, timeout: 30000, withCredentials: true })
apiClient.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/session')) {
    window.dispatchEvent(new Event('session-expired'))
  }
  return Promise.reject(error)
})
export function exportUrl(id, kind) {
  return `${API_BASE}/history/${encodeURIComponent(id)}/${kind}`
}
export default apiClient
