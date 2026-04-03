/**
 * 全局 Toast 通知状态管理。
 */
import { create } from 'zustand'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastMessage {
    id: string
    type: ToastType
    title: string
    description?: string
    duration?: number
}

interface ToastState {
    toasts: ToastMessage[]
    addToast: (toast: Omit<ToastMessage, 'id'>) => void
    removeToast: (id: string) => void
    clearAllToasts: () => void
}

let toastIdCounter = 0

export const useToastStore = create<ToastState>((set) => ({
    toasts: [],
    addToast: (toast) => {
        const id = `toast-${++toastIdCounter}-${Date.now()}`
        const newToast: ToastMessage = {
            id,
            duration: 5000,
            ...toast,
        }
        set((state) => ({
            toasts: [...state.toasts, newToast],
        }))
        if (newToast.duration && newToast.duration > 0) {
            setTimeout(() => {
                set((state) => ({
                    toasts: state.toasts.filter((t) => t.id !== id),
                }))
            }, newToast.duration)
        }
    },
    removeToast: (id) =>
        set((state) => ({
            toasts: state.toasts.filter((t) => t.id !== id),
        })),
    clearAllToasts: () => set({ toasts: [] }),
}))
