import type { TaskEvent } from '@/types/task'

export function describeTaskEvent(ev: TaskEvent | undefined): string {
  if (!ev) return '连接中…'

  switch (ev.kind) {
    case 'plan_created':
      return '已生成执行计划'
    case 'step_start': {
      const title = ev.payload?.title
      return typeof title === 'string' && title.trim()
        ? `执行步骤：${title.trim()}`
        : '步骤开始'
    }
    case 'tool_call':
      return '调用工具'
    case 'tool_result':
      return '工具返回结果'
    case 'error': {
      const msg = ev.payload?.message
      return typeof msg === 'string' ? `出错：${msg}` : '执行出错'
    }
    case 'replan':
      return '正在重规划'
    case 'llm_stream_delta':
      return '输出'
    default:
      return `事件：${ev.kind}`
  }
}
