import type { MouseEvent } from "react";
import { Archive, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface ConversationListProps {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  pendingActionId: string | null;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string) => void;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}

export function ConversationList({
  conversations,
  currentConversationId,
  isLoading,
  pendingActionId,
  onCreate,
  onSelect,
  onRename,
  onArchive,
  onDelete,
}: ConversationListProps) {
  const handleActionClick = (
    event: MouseEvent<HTMLButtonElement>,
    callback: () => void,
  ) => {
    event.stopPropagation();
    callback();
  };

  return (
    <div className="flex w-60 flex-col border-r">
      <div className="flex h-14 items-center justify-between border-b px-3">
        <span className="text-sm font-medium">会话</span>
        <button
          onClick={onCreate}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="新建会话"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-1 overflow-auto p-2">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground">暂无会话</p>
        ) : (
          conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={cn(
                "flex items-start gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                conversation.id === currentConversationId
                  ? "bg-accent font-medium"
                  : "hover:bg-accent/50",
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(conversation.id)}
                className="min-w-0 flex-1 text-left"
              >
                <span className="line-clamp-1 block">
                  {conversation.title || "新会话"}
                </span>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{new Date(conversation.updated_at).toLocaleDateString("zh-CN")}</span>
                  {conversation.status !== "active" && (
                    <span className="rounded-full bg-muted px-1.5 py-0.5">
                      {conversation.status === "closed" ? "已归档" : "已转交"}
                    </span>
                  )}
                </div>
              </button>

              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  disabled={pendingActionId === conversation.id}
                  onClick={(event) => handleActionClick(event, () => onRename(conversation.id))}
                  className="rounded p-1 text-muted-foreground hover:bg-background/70 hover:text-foreground disabled:opacity-50"
                  title="重命名"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  disabled={pendingActionId === conversation.id || conversation.status !== "active"}
                  onClick={(event) => handleActionClick(event, () => onArchive(conversation.id))}
                  className="rounded p-1 text-muted-foreground hover:bg-background/70 hover:text-foreground disabled:opacity-50"
                  title="归档"
                >
                  <Archive className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  disabled={pendingActionId === conversation.id}
                  onClick={(event) => handleActionClick(event, () => onDelete(conversation.id))}
                  className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
