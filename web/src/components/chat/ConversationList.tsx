import { Loader2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface ConversationListProps {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  onCreate: () => void;
  onSelect: (id: string) => void;
}

export function ConversationList({
  conversations,
  currentConversationId,
  isLoading,
  onCreate,
  onSelect,
}: ConversationListProps) {
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
            <button
              key={conversation.id}
              onClick={() => onSelect(conversation.id)}
              className={cn(
                "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                conversation.id === currentConversationId
                  ? "bg-accent font-medium"
                  : "hover:bg-accent/50",
              )}
            >
              <span className="line-clamp-1">
                {conversation.title || "新会话"}
              </span>
              <span className="text-xs text-muted-foreground">
                {new Date(conversation.updated_at).toLocaleDateString("zh-CN")}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
