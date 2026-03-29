/**
 * 设置页：MCP 配置 + Skills 路径（非密钥字段）。
 */

import { useState, useMemo } from 'react'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { useSettings } from '@/hooks/useSettings'

/** 设置表单内容（仅在 settings 加载完成后渲染）。 */
function SettingsForm({
  initialSkillsPaths,
  initialMcp,
  updateSettings,
  isUpdating,
}: {
  initialSkillsPaths: string
  initialMcp: unknown[]
  updateSettings: ReturnType<typeof useSettings>['updateSettings']
  isUpdating: boolean
}) {
  const [skillsPaths, setSkillsPaths] = useState(initialSkillsPaths)
  const [saved, setSaved] = useState(false)

  /** 保存设置。 */
  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    updateSettings(
      {
        mcp: initialMcp,
        skills_paths: skillsPaths
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 2000)
        },
      },
    )
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-8">
      {/* MCP 配置（只读展示） */}
      <section>
        <h2 className="fa-section-title">MCP 连接配置</h2>
        <p className="-mt-2 mb-3 text-neutral-500 text-xs">
          GET/PUT /api/v1/settings · mcp[]。密钥仅通过服务端环境变量配置。
        </p>
        {initialMcp.length === 0 ? (
          <p className="text-neutral-400 text-sm">暂无 MCP 配置</p>
        ) : (
          <pre className="fa-panel max-h-64">{JSON.stringify(initialMcp, null, 2)}</pre>
        )}
      </section>

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
          LLM API Key、MCP 密钥等敏感信息仅通过后端环境变量配置，
          请勿在此页面或前端代码中输入密钥。
        </p>
      </section>

      {/* 提交 */}
      <div className="flex items-center gap-3">
        <button type="submit" disabled={isUpdating} className="fa-btn-primary">
          {isUpdating ? '保存中…' : '保存设置'}
        </button>
        {saved && <span className="text-emerald-600 text-sm">已保存</span>}
      </div>
    </form>
  )
}

export function SettingsPage() {
  const { settings, isLoading, error, updateSettings, isUpdating } = useSettings()

  const initialSkillsPaths = useMemo(
    () => settings?.skills_paths.join('\n') ?? '',
    [settings],
  )

  return (
    <div className="flex flex-1 flex-col">
      <Header title="设置" />

      <div className="mx-auto w-full max-w-2xl px-6 py-8 pb-12">
        {isLoading && <LoadingSpinner />}
        {error && <ErrorAlert message="加载设置失败" />}

        {settings && (
          <SettingsForm
            key={initialSkillsPaths}
            initialSkillsPaths={initialSkillsPaths}
            initialMcp={settings.mcp}
            updateSettings={updateSettings}
            isUpdating={isUpdating}
          />
        )}
      </div>
    </div>
  )
}
