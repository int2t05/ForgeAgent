/**
 * 设置页：MCP / Skills 配置（含保存）在上，工具注册表（只读快照）在下。
 */

import { useMemo, useState } from 'react'
import { Header } from '@/layouts/Header'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { MessageDialog } from '@/components/ui/MessageDialog'
import { McpServersEditor } from '@/components/settings/McpServersEditor'
import { ToolsRegistrySection } from '@/components/settings/ToolsRegistrySection'
import { ExecutionModeSection } from '@/components/settings/ExecutionModeSection'
import { validateSkillPaths } from '@/api/settings'
import { useSettings } from '@/hooks/useSettings'
import {
  parseMcpListFromApi,
  draftsToMcpPayload,
  type McpServerDraft,
} from '@/types/mcp'
import type { Settings, SkillPathsValidateResponse, ExecutionMode } from '@/types/settings'

/** 设置表单内容（仅在 settings 加载完成后渲染）。 */
function SettingsForm({
  initialSkillsPaths,
  initialAgentWorkspaceRoot,
  initialMcp,
  initialExecutionMode,
  updateSettings,
  isUpdating,
  updateError,
}: {
  initialSkillsPaths: string
  initialAgentWorkspaceRoot: string
  initialMcp: unknown[]
  initialExecutionMode: ExecutionMode
  updateSettings: ReturnType<typeof useSettings>['updateSettings']
  isUpdating: boolean
  updateError: ReturnType<typeof useSettings>['updateError']
}) {
  const [skillsPaths, setSkillsPaths] = useState(initialSkillsPaths)
  const [agentWorkspaceRoot, setAgentWorkspaceRoot] = useState(initialAgentWorkspaceRoot)
  const [mcpServers, setMcpServers] = useState<McpServerDraft[]>(() =>
    parseMcpListFromApi(initialMcp),
  )
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(initialExecutionMode)
  const [skillValidate, setSkillValidate] = useState<SkillPathsValidateResponse | null>(null)
  const [skillValidateLoading, setSkillValidateLoading] = useState(false)
  const [skillValidateError, setSkillValidateError] = useState<string | null>(null)

  async function handleValidateSkills() {
    const paths = skillsPaths
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    setSkillValidateError(null)
    if (paths.length === 0) {
      setSkillValidate({ items: [], all_ok: false })
      return
    }
    setSkillValidateLoading(true)
    try {
      const res = await validateSkillPaths(paths)
      setSkillValidate(res)
    } catch (e) {
      setSkillValidate(null)
      setSkillValidateError(e instanceof Error ? e.message : '校验请求失败')
    } finally {
      setSkillValidateLoading(false)
    }
  }

  /** 保存设置。 */
  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    const body: Settings = {
      mcp: draftsToMcpPayload(mcpServers),
      skills_paths: skillsPaths
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
      agent_workspace_root: agentWorkspaceRoot.trim() || null,
      execution_mode: executionMode,
    }
    updateSettings(body)
  }

  return (
    <form onSubmit={handleSave} className="flex max-w-3xl flex-col gap-6">
      <section>
        <h2 className="mb-3 text-base font-semibold text-neutral-800">MCP</h2>
        <McpServersEditor servers={mcpServers} onChange={setMcpServers} />
      </section>

      {updateError && (
        <ErrorAlert
          message="保存失败"
          detail={
            updateError instanceof Error ? updateError.message : '未知错误'
          }
        />
      )}

      <ExecutionModeSection
        value={executionMode}
        onChange={setExecutionMode}
      />

      <section>
        <h2 className="mb-3 text-base font-semibold text-neutral-800">Agent 工作区根目录</h2>
        <textarea
          value={agentWorkspaceRoot}
          onChange={(e) => setAgentWorkspaceRoot(e.target.value)}
          rows={2}
          className="fa-input resize-none font-mono"
          placeholder="绝对路径，或相对仓库根的路径；留空则使用环境变量 AGENT_WORKSPACE_ROOT"
        />
        <p className="fa-text-caption mt-1.5 text-neutral-500">
          保存后工具注册表会立即同步。对话侧栏需再点「刷新」以回到工作区根并刷新列表。
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-neutral-800">Skills</h2>
        <textarea
          value={skillsPaths}
          onChange={(e) => {
            setSkillsPaths(e.target.value)
            setSkillValidate(null)
            setSkillValidateError(null)
          }}
          rows={3}
          className="fa-input resize-none font-mono"
          placeholder="每行一个目录，例如 skills/example_skill"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="fa-btn-secondary py-1.5 text-sm"
            disabled={skillValidateLoading}
            onClick={() => void handleValidateSkills()}
          >
            {skillValidateLoading ? '校验中…' : '校验路径'}
          </button>
          {skillValidate && (
            <span
              className={
                skillValidate.items.length === 0
                  ? 'text-sm text-neutral-500'
                  : skillValidate.all_ok
                    ? 'text-sm text-emerald-700'
                    : 'text-sm text-amber-800'
              }
            >
              {skillValidate.items.length === 0
                ? '请先填写至少一行路径'
                : skillValidate.all_ok
                  ? '上述路径均可用于 Skill 导入'
                  : '部分路径未就绪，请对照下方说明修正'}
            </span>
          )}
        </div>
        {skillValidateError && (
          <p className="fa-text-caption mt-1 text-red-600">{skillValidateError}</p>
        )}
        {skillValidate && skillValidate.items.length > 0 && (
          <ul className="mt-2 space-y-1.5 rounded-md border border-neutral-200 bg-neutral-50/90 p-3 text-xs text-neutral-800">
            {skillValidate.items.map((it, idx) => (
              <li
                key={`${idx}:${it.input_path}:${it.resolved_path}`}
                className={it.ok ? 'text-emerald-800' : 'text-red-800'}
              >
                <span className="select-none">{it.ok ? '✓' : '✗'}</span>{' '}
                <code className="rounded bg-white/80 px-1">{it.input_path}</code>
                <span className="text-neutral-700"> — {it.message}</span>
                {it.resolved_path !== it.input_path && (
                  <div className="mt-0.5 pl-4 font-mono text-[11px] text-neutral-500">
                    → {it.resolved_path}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="fa-text-caption mt-1.5 text-neutral-500">
          目录内需包含 SKILL.md 或 skill.md，规划器才会在 <code className="font-mono">skill_imports</code> 中引用。
        </p>
      </section>

      <p className="fa-text-caption text-neutral-500">密钥请使用环境变量，勿在此填写。</p>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={isUpdating} className="fa-btn-primary">
          {isUpdating ? '保存中…' : '保存'}
        </button>
      </div>
    </form>
  )
}

export function SettingsPage() {
  const {
    settings,
    dataUpdatedAt,
    isLoading,
    error,
    updateSettings: commitSettings,
    isUpdating,
    updateError,
    resetSettings: commitReset,
    isResetting,
    resetError,
  } = useSettings()
  const [confirmReset, setConfirmReset] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackTitle, setFeedbackTitle] = useState('')
  const [feedbackDescription, setFeedbackDescription] = useState<string | undefined>(
    undefined,
  )

  function showFeedback(title: string, description?: string) {
    setFeedbackTitle(title)
    setFeedbackDescription(description)
    setFeedbackOpen(true)
  }

  const updateSettings: typeof commitSettings = (body, options) => {
    commitSettings(body, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showFeedback(
          '配置已保存',
          '设置已写入服务端，工具注册表已更新；对话页工作区侧栏可点「刷新」同步根目录与列表。',
        )
      },
    })
  }

  const resetSettings: typeof commitReset = (variables, options) => {
    commitReset(variables, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showFeedback(
          '已重置',
          'MCP、Skills 与 Agent 工作区根目录已清空（工作区将回退为环境变量）。',
        )
      },
    })
  }

  const initialSkillsPaths = useMemo(
    () => settings?.skills_paths.join('\n') ?? '',
    [settings],
  )

  const initialAgentWorkspaceRoot = useMemo(
    () => settings?.agent_workspace_root?.trim() ?? '',
    [settings],
  )

  const initialExecutionMode: ExecutionMode = settings?.execution_mode ?? 'auto'

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ConfirmDialog
        open={confirmReset}
        title="重置"
        description="清空 MCP、Skills 与工作区根（回退环境变量）。"
        confirmLabel="重置"
        pending={isResetting}
        onCancel={() => !isResetting && setConfirmReset(false)}
        onConfirm={() =>
          resetSettings(undefined, {
            onSuccess: () => setConfirmReset(false),
          })
        }
      />

      <MessageDialog
        open={feedbackOpen}
        title={feedbackTitle}
        description={feedbackDescription}
        onClose={() => setFeedbackOpen(false)}
      />

      <div className="shrink-0">
        <Header
          title="设置"
          actions={
            <button
              type="button"
              className="fa-btn-secondary py-1.5"
              disabled={isResetting || isLoading}
              onClick={() => setConfirmReset(true)}
            >
              重置
            </button>
          }
        />
      </div>

      <div className="fa-reveal min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto w-full max-w-3xl px-6 py-6 pb-10">
          {isLoading && <LoadingSpinner />}
          {error && <ErrorAlert message="加载设置失败" />}

          {resetError && (
            <ErrorAlert
              message="重置失败"
              detail={
                resetError instanceof Error ? resetError.message : '未知错误'
              }
            />
          )}

          {settings && (
            <SettingsForm
              key={dataUpdatedAt}
              initialSkillsPaths={initialSkillsPaths}
              initialAgentWorkspaceRoot={initialAgentWorkspaceRoot}
              initialMcp={settings.mcp}
              initialExecutionMode={initialExecutionMode}
              updateSettings={updateSettings}
              isUpdating={isUpdating}
              updateError={updateError}
            />
          )}

          <div className="mt-10 border-t border-neutral-200/90 pt-10">
            <ToolsRegistrySection />
          </div>
        </div>
      </div>
    </div>
  )
}
