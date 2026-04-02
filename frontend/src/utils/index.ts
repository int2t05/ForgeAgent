/**
 * 前端工具函数集：按业务域分组，与后端模块对齐。
 *
 * - **任务域**（task）：计划步骤、事件描述、时间线、执行流处理
 * - **聊天域**（chat）：LLM 流式折叠、思考解析、消息处理
 * - **通用域**（common）：格式化、错误详情、SSE 解析、滚动检测
 */

/** 任务域：与后端 execution/planning 模块对齐 */
export { describeTaskEvent } from './describeTaskEvent'
export { buildTimelineRenderables } from './groupTaskEvents'
export type { TimelineRenderable } from './groupTaskEvents'
export {
  derivePlanTodoProgress,
  latestPlanStepsFromEvents,
  normalizePlanStepsFromUnknown,
} from './normalizeTaskPlan'
export type { PlanStep, PlanTodoProgress } from './normalizeTaskPlan'
export { resolvePlanStepsAfterComposerStop } from './resolvePlanStepsAfterComposerStop'

/** 聊天域：LLM 流式输出与消息展示 */
export {
  COMPOSER_WRITE_PREVIEW_LINES,
  buildComposerRoundSegments,
  composerRoundsHaveContent,
  composerRoundsPayloadLength,
  foldComposerLlmStream,
  foldComposerLlmStreamForBusy,
  foldComposerLlmStreamForFreeze,
  planCycleAnchorSeq,
  shouldShowComposerRoundThought,
  sliceTaskEventsForActivePlanCycle,
} from './foldComposerLlmStream'
export type {
  ComposerActionBlock,
  ComposerRoundSegment,
  ComposerToolActionPanel,
} from './foldComposerLlmStream'
export { foldLlmStreamDeltas } from './foldLlmStreamDeltas'
export { parseMessageThinking } from './parseMessageThinking'
export { streamThinkAnswer } from './streamThinkAnswer'

/** 通用域：格式化、错误处理、SSE、UI 工具 */
export { errDetail } from './errDetail'
export { formatDateTime, formatRelativeTime } from './format'
export { isNearScrollBottom } from './isNearScrollBottom'
export { estimateContextTokens } from './estimateContextTokens'
export { parseSseDataJson, splitSseBlocks } from './sseParse'
export { sessionListSnippetText } from './sessionListSnippet'
