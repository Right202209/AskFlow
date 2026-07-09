import type { KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";

interface ChatComposerProps {
  input: string;
  isStreaming: boolean;
  canSend: boolean;
  connectionHint: string | null;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}

export function ChatComposer({
  input,
  isStreaming,
  canSend,
  connectionHint,
  onInputChange,
  onSend,
  onCancel,
}: ChatComposerProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSend();
    }
  };

  return (
    <div className="border-t p-4">
      <div className="space-y-2">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            rows={1}
            className="flex-1 resize-none rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          {isStreaming ? (
            <button
              onClick={onCancel}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border text-muted-foreground hover:bg-accent"
              title="停止生成"
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={onSend}
              disabled={!canSend}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-50"
              title="发送"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
        {connectionHint && (
          <p className="text-xs text-muted-foreground">{connectionHint}</p>
        )}
      </div>
    </div>
  );
}
