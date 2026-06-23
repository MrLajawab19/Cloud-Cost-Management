// src/api/client.js — Axios instance pointing to the FastAPI backend

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ── API Methods ──────────────────────────────────────────────────

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
