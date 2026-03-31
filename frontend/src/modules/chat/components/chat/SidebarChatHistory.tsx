import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SessionListPanel } from '@/modules/chat/components/chat/SessionListPanel'
import { ConfirmDialog } from '@/modules/shell/components/common/ConfirmDialog'
import { ErrorAlert } from '@/modules/shell/components/common/ErrorAlert'
import { errDetail } from '@/core/lib/errDetail'
import { deleteSession } from '@/modules/sessions/api/sessions'
import { useSession } from '@/modules/sessions/hooks/useSession'
import { useSessionStore } from '@/modules/sessions/stores/sessionStore'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/modules/tasks/hooks/usePendingComposerTask'
import { useComposerTaskStore } from '@/modules/tasks/stores/composerTaskStore'

export function SidebarChatHistory() {
  const queryClient = useQueryClient()
  const { clearSession } = useSession()
  const sessionId = useSessionStore((s) => s.sessionId)
  const busy = usePendingComposerTaskBusy()
  const { pendingSessionId } = usePendingComposerTaskMeta()
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(
    null,
  )

  const deleteSessionMutation = useMutation({
    mutationFn: (sid: string) => deleteSession(sid),
    onSuccess: (_data, sid) => {
      setConfirmDeleteSessionId(null)
      useComposerTaskStore.getState().clearStickyPlanForSession(sid)
      void queryClient.removeQueries({ queryKey: ['session', sid, 'messages'] })
      void queryClient.removeQueries({ queryKey: ['session', sid, 'detail'] })
      void queryClient.removeQueries({ queryKey: ['tasks', 'session', sid] })
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      if (sid === useSessionStore.getState().sessionId) clearSession()
    },
  })

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <ConfirmDialog
        open={confirmDeleteSessionId != null}
        title="删除会话"
        description="将删除本会话下的全部消息与任务记录，且无法恢复。若仍有任务在执行，将无法删除。"
        confirmLabel="删除会话"
        pending={deleteSessionMutation.isPending}
        onCancel={() =>
          !deleteSessionMutation.isPending && setConfirmDeleteSessionId(null)
        }
        onConfirm={() => {
          if (confirmDeleteSessionId)
            deleteSessionMutation.mutate(confirmDeleteSessionId)
        }}
      />
      {deleteSessionMutation.error ? (
        <div className="shrink-0 px-2 pt-1">
          <ErrorAlert
            message="删除会话失败"
            detail={errDetail(deleteSessionMutation.error)}
          />
        </div>
      ) : null}
      <SessionListPanel
        currentSessionHasRunningTask={
          Boolean(busy && sessionId && sessionId === pendingSessionId)
        }
        onRequestDeleteSession={(sid) => setConfirmDeleteSessionId(sid)}
        deleteSessionPending={deleteSessionMutation.isPending}
      />
    </div>
  )
}
