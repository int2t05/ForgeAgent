/**
 * 底栏输入区：环形进度，表示估算上下文用量相对模型窗口的比例（类似 Cursor 用量环）。
 */

import { memo, useMemo } from 'react'

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x))
}

export interface ComposerContextRingProps {
  /** 估算已占用 tokens */
  usedTokens: number
  /** 模型上下文窗口 tokens（总分母） */
  windowTokens: number
  className?: string
  /** SVG 视口边长（CSS px） */
  size?: number
}

export const ComposerContextRing = memo(function ComposerContextRing({
  usedTokens,
  windowTokens,
  className = '',
  size = 22,
}: ComposerContextRingProps) {
  const ratio = windowTokens > 0 ? usedTokens / windowTokens : 0
  const pct = Math.round(clamp01(ratio) * 100)

  const { strokeClass, trackClass } = useMemo(() => {
    if (ratio >= 1)
      return { strokeClass: 'text-red-500', trackClass: 'text-neutral-300/90' }
    if (ratio >= 0.85)
      return { strokeClass: 'text-amber-500', trackClass: 'text-neutral-300/90' }
    return { strokeClass: 'text-neutral-600', trackClass: 'text-neutral-300/90' }
  }, [ratio])

  const v = 32
  const c = v / 2
  const r = 12
  const stroke = 3
  const circ = 2 * Math.PI * r
  const dash = circ * clamp01(ratio)

  const label =
    windowTokens > 0
      ? `估算上下文用量约 ${pct}%（约 ${usedTokens.toLocaleString('zh-CN')} / ${windowTokens.toLocaleString('zh-CN')} tokens）`
      : '上下文窗口未配置'

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${className}`}
      title={label}
      role="img"
      aria-label={label}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${v} ${v}`}
        fill="none"
        className="overflow-visible"
        aria-hidden
      >
        <circle
          cx={c}
          cy={c}
          r={r}
          strokeWidth={stroke}
          className={trackClass}
          stroke="currentColor"
          fill="none"
          opacity={0.45}
        />
        <circle
          cx={c}
          cy={c}
          r={r}
          strokeWidth={stroke}
          className={strokeClass}
          stroke="currentColor"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          transform={`rotate(-90 ${c} ${c})`}
        />
      </svg>
    </span>
  )
})
