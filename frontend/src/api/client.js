// src/api/client.js — Axios instance pointing to the FastAPI backend

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor to attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  
  const accountId = localStorage.getItem('active_account_id')
  if (accountId && !config.url.startsWith('/auth')) {
    // Attach account_id to params
    config.params = { ...config.params, account_id: accountId }
  }
  return config
}, (error) => {
  return Promise.reject(error)
})

// ── API Methods ──────────────────────────────────────────────────

export const authAPI = {
  login:    (formData) => api.post('/auth/login', formData, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }),
  register: (data)     => api.post('/auth/register', data),
  me:       ()         => api.get('/auth/me'),
}

export const accountsAPI = {
  list:   ()     => api.get('/accounts/'),
  create: (data) => api.post('/accounts/'),
  delete: (id)   => api.delete(`/accounts/${id}`),
  sync:   ()     => api.post('/accounts/sync'),
}

export const resourcesAPI = {
  list:    (params = {}) => api.get('/resources/', { params }),
  summary: ()            => api.get('/resources/summary'),
  get:     (id)          => api.get(`/resources/${id}`),
}

export const costsAPI = {
  summary:      ()              => api.get('/costs/summary'),
  trend:        (days = 30)     => api.get('/costs/trend', { params: { days } }),
  byService:    ()              => api.get('/costs/by-service'),
  topResources: (limit = 8)    => api.get('/costs/top-resources', { params: { limit } }),
}

export const recommendationsAPI = {
  list:    (params = {})  => api.get('/recommendations/', { params }),
  summary: ()             => api.get('/recommendations/summary'),
  resolve: (id)           => api.post(`/recommendations/${id}/resolve`),
  refresh: ()             => api.post('/recommendations/refresh'),
}

export const predictionsAPI = {
  get: () => api.get('/predictions/'),
}

export const healthAPI = {
  check: () => api.get('/health'),
}

export default api
