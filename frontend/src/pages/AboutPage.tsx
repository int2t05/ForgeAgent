/**
 * 关于页：MVP 边界说明与帮助信息。
 */

import { Header } from '@/components/layout/Header'

export function AboutPage() {
  return (
    <div className="flex flex-1 flex-col">
      <Header title="关于" />

      <div className="mx-auto w-full max-w-2xl px-6 py-8 pb-12">
        <article className="space-y-8">
          <header>
            <h2 className="text-lg font-semibold text-neutral-900 tracking-tight">ForgeAgent</h2>
            <p className="mt-2 text-neutral-600 text-sm leading-relaxed">
              ForgeAgent 是一款 AI Agent
              应用，在单一产品内提供规划、记忆、工具、执行四类能力模块，采用
              Plan-and-Execute（先规划后执行）的认知循环。
            </p>
          </header>

          <section>
            <h3 className="fa-section-title">MVP 边界</h3>
            <ul className="space-y-2 text-neutral-600 text-sm">
              <li className="flex gap-2">
                <span className="text-primary-500">·</span>
                单 Agent + 显式规划循环
              </li>
              <li className="flex gap-2">
                <span className="text-primary-500">·</span>
                会话级记忆（当前会话内消息与中间状态）
              </li>
              <li className="flex gap-2">
                <span className="text-primary-500">·</span>
                统一工具注册表（内置 / MCP / Skills）
              </li>
              <li className="flex gap-2">
                <span className="text-primary-500">·</span>
                可观测执行（结构化事件流、执行时间线）
              </li>
            </ul>
          </section>

          <section>
            <h3 className="fa-section-title">不在 MVP 范围</h3>
            <ul className="space-y-2 text-neutral-500 text-sm">
              <li className="flex gap-2">
                <span className="text-neutral-300">·</span>
                多 Agent 生产级编排
              </li>
              <li className="flex gap-2">
                <span className="text-neutral-300">·</span>
                完整多租户 SaaS 与计费
              </li>
              <li className="flex gap-2">
                <span className="text-neutral-300">·</span>
                拖拽式复杂工作流画布
              </li>
              <li className="flex gap-2">
                <span className="text-neutral-300">·</span>
                完整长期记忆治理与 RAG
              </li>
            </ul>
          </section>

          <section>
            <h3 className="fa-section-title">四大能力模块</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="fa-card p-4">
                <p className="font-medium text-neutral-800 text-sm">规划 Planning</p>
                <p className="mt-1 text-neutral-500 text-xs leading-relaxed">
                  生成 / 更新任务计划，结构化步骤
                </p>
              </div>
              <div className="fa-card p-4">
                <p className="font-medium text-neutral-800 text-sm">记忆 Memory</p>
                <p className="mt-1 text-neutral-500 text-xs leading-relaxed">
                  当前会话上下文与短期状态
                </p>
              </div>
              <div className="fa-card p-4">
                <p className="font-medium text-neutral-800 text-sm">工具 Tool</p>
                <p className="mt-1 text-neutral-500 text-xs leading-relaxed">
                  统一注册与调用：内置 / MCP / Skill
                </p>
              </div>
              <div className="fa-card p-4">
                <p className="font-medium text-neutral-800 text-sm">执行 Execution</p>
                <p className="mt-1 text-neutral-500 text-xs leading-relaxed">
                  按计划逐步执行并写回状态
                </p>
              </div>
            </div>
          </section>

          <section>
            <h3 className="fa-section-title">Skills 说明</h3>
            <p className="text-neutral-600 text-sm leading-relaxed">
              Skills 作为约定目录下的预置资源包，加载后映射到已有工具 / 提示模板，与 MCP
              共用「工具注册」机制，在同一注册表中统一展示与消费。
            </p>
          </section>
        </article>
      </div>
    </div>
  )
}
