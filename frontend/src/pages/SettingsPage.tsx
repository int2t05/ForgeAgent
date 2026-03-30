/**
 * 设置页：MCP 配置 + Skills 路径（非密钥字段）。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { McpServersEditor } from '@/components/settings/McpServersEditor'
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

      <p className="fa-text-caption text-neutral-400">密钥请使用环境变量，勿在此填写。</p>

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
  const [notice, setNotice] = useState<string | null>(null)
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function showNotice(message: string, ms = 4500) {
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current)
    setNotice(message)
    noticeTimerRef.current = setTimeout(() => {
      setNotice(null)
      noticeTimerRef.current = null
    }, ms)
  }

  useEffect(() => {
    return () => {
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current)
    }
  }, [])

  const updateSettings: typeof commitSettings = (body, options) => {
    commitSettings(body, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showNotice('已保存')
      },
    })
  }

  const resetSettings: typeof commitReset = (variables, options) => {
    commitReset(variables, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showNotice('已重置')
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
        {notice && (
          <div
            role="status"
            aria-live="polite"
            className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-emerald-200/90 bg-emerald-50/90 px-3 py-2 text-base text-emerald-900"
          >
            <p className="leading-snug">{notice}</p>
            <button
              type="button"
              className="shrink-0 text-emerald-600 transition-colors hover:text-emerald-800"
              aria-label="关闭提示"
              onClick={() => {
                if (noticeTimerRef.current) {
                  clearTimeout(noticeTimerRef.current)
                  noticeTimerRef.current = null
                }
                setNotice(null)
              }}
            >
              ✕
            </button>
          </div>
        )}
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
        </div>
      </div>
    </div>
  )
}
