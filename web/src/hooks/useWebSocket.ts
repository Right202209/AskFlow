import { useCallback, useEffect, useRef } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import type { ClientMessage, ServerMessage } from "@/types/chat";

const HEARTBEAT_INTERVAL = 30_000;
const RECONNECT_BASE_DELAY = 1_000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function useWebSocket() {
  const token = useAuthStore((s) => s.token);
  const appendToken = useChatStore((s) => s.appendToken);
  const finalizeMessage = useChatStore((s) => s.finalizeMessage);
  const setIntent = useChatStore((s) => s.setIntent);
  const setSources = useChatStore((s) => s.setSources);

  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectAttempts = useRef(0);
  const conversationIdRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }
    wsRef.current = null;
  }, []);

  const connect = useCallback(() => {
    if (!token) return;
    cleanup();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/chat/ws/${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          const ping: ClientMessage = { type: "ping", timestamp: Date.now() };
          ws.send(JSON.stringify(ping));
        }
      }, HEARTBEAT_INTERVAL);
    };

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      switch (msg.type) {
        case "token":
          appendToken((msg.data?.content as string) ?? "");
          break;
        case "message_end":
          if (msg.conversation_id) finalizeMessage(msg.conversation_id);
          break;
        case "intent":
          setIntent({
            label: msg.data?.label as string,
            confidence: msg.data?.confidence as number,
          });
          break;
        case "source":
          setSources((msg.data?.sources as Array<{ title: string; chunk: string; score: number }>) ?? []);
          break;
        case "error":
          console.error("WebSocket error:", msg.data);
          break;
        case "pong":
          break;
      }
    };

    ws.onclose = () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts.current);
        reconnectAttempts.current++;
        setTimeout(connect, delay);
      }
    };
  }, [token, cleanup, appendToken, finalizeMessage, setIntent, setSources]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  const sendMessage = useCallback((conversationId: string, content: string) => {
    conversationIdRef.current = conversationId;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const msg: ClientMessage = {
        type: "message",
        conversation_id: conversationId,
        content,
        timestamp: Date.now(),
      };
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const cancelGeneration = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const msg: ClientMessage = { type: "cancel", timestamp: Date.now() };
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;

  return { sendMessage, cancelGeneration, isConnected };
}
