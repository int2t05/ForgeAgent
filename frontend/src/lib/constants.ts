/**
 * 全局常量：API 基础 URL、状态颜色映射、分页默认值。
 */

import type { TaskStatus } from '@/types/task'

/** 后端 API 根 URL（由 Vite 环境变量注入，默认本地开发地址）。 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

/** 分页默认参数。 */
export const DEFAULT_PAGE_SIZE = 20
export const MAX_PAGE_SIZE = 100

/**
 * 任务状态 → Tailwind 颜色类映射（背景 + 文字）。
 * 遵循 PRD「中性背景 + 单一强调色区分状态」。
 */
export const STATUS_COLOR_MAP: Record<
  TaskStatus,
  { bg: string; text: string; dot: string }
> = {
  pending: {
    bg: 'bg-neutral-100',
    text: 'text-neutral-600',
    dot: 'bg-neutral-400',
  },
  running: {
    bg: 'bg-primary-50',
    text: 'text-primary-700',
    dot: 'bg-primary-500',
  },
  success: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    dot: 'bg-emerald-500',
  },
  failed: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    dot: 'bg-red-500',
  },
  cancelled: {
    bg: 'bg-neutral-100',
    text: 'text-neutral-500',
    dot: 'bg-neutral-400',
  },
}

/** 任务状态中文标签。 */
export const STATUS_LABEL_MAP: Record<TaskStatus, string> = {
  pending: '等待中',
  running: '执行中',
  success: '已完成',
  failed: '已失败',
  cancelled: '已取消',
}

/** 终态集合：用于前端判断任务是否已结束。 */
export const TERMINAL_STATUSES: Set<TaskStatus> = new Set([
  'success',
  'failed',
  'cancelled',
])
