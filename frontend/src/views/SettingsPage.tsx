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
import { useSettings } from '@/hooks/useSettings'
import {
  parseMcpListFromApi,
  draftsToMcpPayload,
  type McpServerDraft,
} from '@/types/mcp'
import type { Settings } from '@/types/settings'

/** 设置表单内容（仅在 settings 加载完成后渲染）。 */
function SettingsForm({
  initialSkillsPaths,
  initialMcp,
  updateSettings,
  isUpdating,
  updateError,
}: {
  initialSkillsPaths: string
  initialMcp: unknown[]
  updateSettings: ReturnType<typeof useSettings>['updateSettings']
  isUpdating: boolean
  updateError: ReturnType<typeof useSettings>['updateError']
}) {
  const [skillsPaths, setSkillsPaths] = useState(initialSkillsPaths)
  const [mcpServers, setMcpServers] = useState<McpServerDraft[]>(() =>
    parseMcpListFromApi(initialMcp),
  )

  /** 保存设置。 */
  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    const body: Settings = {
      mcp: draftsToMcpPayload(mcpServers),
      skills_paths: skillsPaths
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
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

      <section>
        <h2 className="mb-3 text-base font-semibold text-neutral-800">Skills</h2>
        <textarea
          value={skillsPaths}
          onChange={(e) => setSkillsPaths(e.target.value)}
          rows={3}
          className="fa-input resize-none font-mono"
          placeholder="每行一个目录，例如 skills/"
        />
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
          'MCP 与 Skills 已写入服务端，下方工具注册表会自动更新；也可手动点「刷新列表」。',
        )
      },
    })
  }

  const resetSettings: typeof commitReset = (variables, options) => {
    commitReset(variables, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showFeedback('已重置', 'MCP 与 Skills 列表已清空。')
      },
    })
  }

  const initialSkillsPaths = useMemo(
    () => settings?.skills_paths.join('\n') ?? '',
    [settings],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ConfirmDialog
        open={confirmReset}
        title="重置"
        description="清空 MCP 与 Skills 列表。"
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
            initialMcp={settings.mcp}
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
