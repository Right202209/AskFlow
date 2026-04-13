import type { ComponentType } from "react";
import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToastStore, type ToastItem } from "@/stores/toastStore";

const VARIANT_STYLES: Record<ToastItem["variant"], string> = {
  success: "border-green-200 bg-green-50 text-green-950",
  error: "border-red-200 bg-red-50 text-red-950",
  info: "border-slate-200 bg-white text-slate-950",
};

const VARIANT_ICON_STYLES: Record<ToastItem["variant"], string> = {
  success: "text-green-600",
  error: "text-red-600",
  info: "text-slate-600",
};

const VARIANT_ICONS: Record<ToastItem["variant"], ComponentType<{ className?: string }>> = {
  success: CheckCircle2,
  error: TriangleAlert,
  info: Info,
};

export function ToastViewport() {
  const toasts = useToastStore((state) => state.toasts);
  const dismissToast = useToastStore((state) => state.dismissToast);

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-full max-w-sm flex-col gap-3">
      {toasts.map((toast) => {
        const Icon = VARIANT_ICONS[toast.variant];

        return (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto rounded-lg border shadow-lg backdrop-blur",
              VARIANT_STYLES[toast.variant],
            )}
          >
            <div className="flex items-start gap-3 p-4">
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", VARIANT_ICON_STYLES[toast.variant])} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{toast.title}</p>
                {toast.description && (
                  <p className="mt-1 text-sm opacity-80">{toast.description}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismissToast(toast.id)}
                className="rounded p-1 opacity-60 transition hover:bg-black/5 hover:opacity-100"
                title="关闭通知"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
