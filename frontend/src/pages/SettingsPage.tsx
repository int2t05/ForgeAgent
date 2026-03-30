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
    <form onSubmit={handleSave} className="flex max-w-3xl flex-col gap-8">
      <section>
        <h2 className="fa-section-title">MCP 服务</h2>
        <p className="-mt-2 mb-4 text-neutral-500 text-xs leading-relaxed">
          通过下方表单维护 <code className="font-mono text-[11px]">PUT /api/v1/settings</code> 中的{' '}
          <code className="font-mono text-[11px]">mcp</code> 数组。保存后工具注册表会刷新。
        </p>
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

      {/* Skills 路径 */}
      <section>
        <h2 className="fa-section-title">Skills 路径</h2>
        <p className="-mt-2 mb-3 text-neutral-500 text-xs">skills_paths，每行一个目录。</p>
        <textarea
          value={skillsPaths}
          onChange={(e) => setSkillsPaths(e.target.value)}
          rows={4}
          className="fa-input resize-none font-mono"
          placeholder="skills/"
        />
      </section>

      {/* 安全提示 */}
      <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <p className="font-medium">安全提示</p>
        <p className="mt-1 text-xs text-amber-700">
          LLM API Key、MCP 访问密钥等敏感信息仅通过后端环境变量或服务端配置文件提供，
          请勿在本页填写；请求体中若出现 api_key、secret、token 等字段名将被服务端拒绝。
        </p>
      </section>

      {/* 提交 */}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={isUpdating} className="fa-btn-primary">
          {isUpdating ? '保存中…' : '保存设置'}
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
        showNotice('设置已保存，工具列表已刷新。')
      },
    })
  }

  const resetSettings: typeof commitReset = (variables, options) => {
    commitReset(variables, {
      ...options,
      onSuccess: (data, variables, onMutateResult, context) => {
        options?.onSuccess?.(data, variables, onMutateResult, context)
        showNotice('已清空 MCP 与 Skills 路径配置。')
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
        title="重置设置"
        description="将 MCP 列表与 Skills 路径清空为默认空列表（不修改环境变量中的密钥）。"
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
            className="fa-btn-secondary border-amber-200 py-1.5 text-amber-900 text-xs hover:bg-amber-50"
            disabled={isResetting || isLoading}
            onClick={() => setConfirmReset(true)}
          >
            重置列表
          </button>
        }
      />
      </div>

      <div className="fa-reveal min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto w-full max-w-3xl px-6 py-8 pb-12">
        {notice && (
          <div
            role="status"
            aria-live="polite"
            className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 shadow-sm"
          >
            <p className="font-medium leading-relaxed">{notice}</p>
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
