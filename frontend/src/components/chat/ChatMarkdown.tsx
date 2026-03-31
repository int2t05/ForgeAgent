/**
 * 对话气泡内 Markdown 渲染（GFM）；默认安全、无 raw HTML。
 * 围栏代码块：豆包式顶栏（语言标签 + 复制）+ 深色内容区；rehype-highlight 语法着色。
 */

import {
  Children,
  cloneElement,
  isValidElement,
  memo,
  useCallback,
  useEffect,
  useId,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import type { Components } from 'react-markdown'
import 'highlight.js/styles/github-dark.css'

const LANG_LABELS: Record<string, string> = {
  bash: 'Bash',
  sh: 'Shell',
  shell: 'Shell',
  zsh: 'Zsh',
  cpp: 'C++',
  cxx: 'C++',
  c: 'C',
  cs: 'C#',
  csharp: 'C#',
  css: 'CSS',
  diff: 'Diff',
  go: 'Go',
  html: 'HTML',
  xml: 'XML',
  java: 'Java',
  js: 'JavaScript',
  javascript: 'JavaScript',
  jsx: 'JSX',
  json: 'JSON',
  kt: 'Kotlin',
  kotlin: 'Kotlin',
  md: 'Markdown',
  markdown: 'Markdown',
  php: 'PHP',
  py: 'Python',
  python: 'Python',
  rb: 'Ruby',
  ruby: 'Ruby',
  rust: 'Rust',
  sql: 'SQL',
  swift: 'Swift',
  ts: 'TypeScript',
  typescript: 'TypeScript',
  tsx: 'TSX',
  yaml: 'YAML',
  yml: 'YAML',
  dockerfile: 'Dockerfile',
  plaintext: '纯文本',
  text: '纯文本',
}

function langLabel(raw: string): string {
  const k = raw.toLowerCase()
  if (!k) return '纯文本'
  return LANG_LABELS[k] ?? raw
}

function extractTextFromNode(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractTextFromNode).join('')
  if (isValidElement(node)) {
    const props = node.props as { children?: ReactNode }
    return extractTextFromNode(props.children)
  }
  return ''
}

/** 与常见 Markdown 围栏一致：块末尾的多余换行不应复制进剪贴板 */
function textForClipboard(raw: string): string {
  return raw.replace(/\r\n/g, '\n').trimEnd()
}

function IconCopy({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M8 7V5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2M8 7h8a2 2 0 012 2v2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconExpand({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M9 3H5a2 2 0 00-2 2v4M21 9V5a2 2 0 00-2-2h-4M3 15v4a2 2 0 002 2h4M15 21h4a2 2 0 002-2v-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconClose({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M18 6L6 18M6 6l12 12"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

function CodeFence({ children }: { children?: ReactNode }) {
  const dialogTitleId = useId()
  const childArr = Children.toArray(children)
  const codeEl = childArr.find(
    (c): c is ReactElement<{ className?: string; children?: ReactNode }> =>
      isValidElement(c) && c.type === 'code',
  )

  const cls = codeEl?.props.className ?? ''
  const langMatch = /(?:^|\s)language-([\w-+]+)/.exec(cls)
  const rawLang = langMatch?.[1] ?? ''
  const label = langLabel(rawLang)
  const text = codeEl
    ? extractTextFromNode(codeEl.props.children)
    : extractTextFromNode(children)

  const expandPreChildren = codeEl
    ? cloneElement(codeEl, { key: 'fa-code-block-expand' })
    : children

  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(textForClipboard(text))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }, [text])

  useEffect(() => {
    if (!expanded) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [expanded])

  const toolbarActions = (
    <>
      <button
        type="button"
        className="fa-code-block-toolbtn"
        onClick={() => setExpanded(true)}
        aria-label="放大查看代码"
      >
        <IconExpand className="fa-code-block-toolbtn-icon" />
        <span className="fa-code-block-toolbtn-label">放大</span>
      </button>
      <button
        type="button"
        onClick={() => void onCopy()}
        className="fa-code-block-toolbtn"
        aria-label={copied ? '已复制' : '复制代码'}
      >
        {copied ? (
          <span className="fa-code-block-toolbtn-label">已复制</span>
        ) : (
          <>
            <IconCopy className="fa-code-block-toolbtn-icon" />
            <span className="fa-code-block-toolbtn-label">复制</span>
          </>
        )}
      </button>
    </>
  )

  return (
    <div className="fa-code-block">
      <div className="fa-code-block-toolbar">
        <span className="fa-code-block-lang">{label}</span>
        <div className="fa-code-block-toolbar-actions">{toolbarActions}</div>
      </div>
      <div className="fa-code-block-body">
        {/* 保留 react-markdown + rehype-highlight 已生成的 code/hljs 子树 */}
        <pre className="fa-code-block-pre">{children}</pre>
      </div>

      {expanded
        ? createPortal(
            <div
              className="fa-code-block-overlay"
              role="presentation"
              onClick={() => setExpanded(false)}
            >
              <div
                className="fa-code-block-expand-panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby={dialogTitleId}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="fa-code-block-toolbar">
                  <span className="fa-code-block-lang" id={dialogTitleId}>
                    {label}
                  </span>
                  <div className="fa-code-block-toolbar-actions">
                    {toolbarActions}
                    <button
                      type="button"
                      className="fa-code-block-toolbtn"
                      onClick={() => setExpanded(false)}
                      aria-label="关闭放大"
                    >
                      <IconClose className="fa-code-block-toolbtn-icon" />
                    </button>
                  </div>
                </div>
                <div className="fa-code-block-expand-body">
                  <pre className="fa-code-block-pre fa-code-block-pre--expanded">
                    {expandPreChildren}
                  </pre>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}

const mdLink: Partial<Components> = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="fa-md-link underline decoration-primary-500/40 underline-offset-2 transition-colors hover:decoration-primary-600"
    >
      {children}
    </a>
  ),
}

interface ChatMarkdownProps {
  content: string
  variant: 'assistant' | 'user'
}

export const ChatMarkdown = memo(function ChatMarkdown({
  content,
  variant,
}: ChatMarkdownProps) {
  if (!content.trim()) return null

  const className =
    variant === 'user' ? 'fa-md-chat fa-md-chat-user' : 'fa-md-chat'

  const components: Partial<Components> = {
    ...mdLink,
    pre: ({ children }) => <CodeFence>{children}</CodeFence>,
  }

  return (
    <div className={className}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </Markdown>
    </div>
  )
})
