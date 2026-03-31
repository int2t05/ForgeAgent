/**
 * HTTP 请求封装：基于 fetch，统一 baseURL 与错误处理。
 * 所有业务 API 函数均通过本模块发起请求。
 */

import { API_BASE_URL } from '@/config/env'

/** 后端统一错误响应格式（对齐 API.md §1.1）。 */
export interface ApiError {
  detail: string
  code?: string
}

/** 请求异常：携带 HTTP 状态码与结构化错误信息。 */
export class ApiRequestError extends Error {
  status: number
  body: ApiError

  constructor(status: number, body: ApiError) {
    super(body.detail)
    this.name = 'ApiRequestError'
    this.status = status
    this.body = body
  }
}

/**
 * 拼接完整 URL（去除 baseURL 尾部斜杠与 path 前导斜杠的重复）。
 */
function buildUrl(path: string, params?: Record<string, string>): string {
  const base = API_BASE_URL.replace(/\/+$/, '')
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${base}${cleanPath}`)

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, value)
      }
    }
  }
  return url.toString()
}

/**
 * 通用 JSON 请求。
 * @throws {ApiRequestError} 非 2xx 响应时抛出结构化错误
 */
async function request<T>(
  method: string,
  path: string,
  options?: {
    body?: unknown
    params?: Record<string, string>
  },
): Promise<T> {
  const url = buildUrl(path, options?.params)
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  const res = await fetch(url, {
    method,
    headers,
    body: options?.body != null ? JSON.stringify(options.body) : undefined,
  })

  if (!res.ok) {
    let errorBody: ApiError
    try {
      errorBody = (await res.json()) as ApiError
    } catch {
      errorBody = { detail: res.statusText || '请求失败' }
    }
    throw new ApiRequestError(res.status, errorBody)
  }

  return (await res.json()) as T
}

/** GET 请求。 */
export function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  return request<T>('GET', path, { params })
}

/** POST 请求。 */
export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, { body })
}

/** PUT 请求。 */
export function put<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PUT', path, { body })
}

/** PATCH 请求。 */
export function patch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PATCH', path, { body })
}

/** DELETE 请求。 */
export function del<T>(path: string): Promise<T> {
  return request<T>('DELETE', path)
}
