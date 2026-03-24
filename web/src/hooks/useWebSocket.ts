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
  const connectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectAttempts = useRef(0);
  const shouldReconnectRef = useRef(false);
  const conversationIdRef = useRef<string | null>(null);

  const clearTimers = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = undefined;
    }
    if (connectTimerRef.current) {
      clearTimeout(connectTimerRef.current);
      connectTimerRef.current = undefined;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = undefined;
    }
  }, []);

  const disposeSocket = useCallback((socket: WebSocket | null) => {
    if (!socket) return;

    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;

    if (socket.readyState === WebSocket.CONNECTING) {
      // Avoid closing a socket before the handshake finishes, which triggers
      // a false error in React Strict Mode's development-only remount cycle.
      socket.onopen = () => {
        socket.onopen = null;
        socket.close();
      };
      return;
    }

    socket.onopen = null;
    if (socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  }, []);

  const cleanup = useCallback(() => {
    clearTimers();
    disposeSocket(wsRef.current);
    wsRef.current = null;
  }, [clearTimers, disposeSocket]);

  const connect = useCallback(() => {
    if (!token) return;

    clearTimers();
    disposeSocket(wsRef.current);
    wsRef.current = null;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/chat/ws/${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) {
        ws.close();
        return;
      }

      reconnectAttempts.current = 0;
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          const ping: ClientMessage = { type: "ping", timestamp: Date.now() };
          ws.send(JSON.stringify(ping));
        }
      }, HEARTBEAT_INTERVAL);
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;

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
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = undefined;
      }
      if (!shouldReconnectRef.current || reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) return;

      const delay = RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts.current);
      reconnectAttempts.current++;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = undefined;
        connect();
      }, delay);
    };
  }, [token, clearTimers, disposeSocket, appendToken, finalizeMessage, setIntent, setSources]);

  useEffect(() => {
    if (!token) {
      shouldReconnectRef.current = false;
      reconnectAttempts.current = 0;
      cleanup();
      return;
    }

    shouldReconnectRef.current = true;
    connectTimerRef.current = setTimeout(() => {
      connectTimerRef.current = undefined;
      connect();
    }, 0);

    return () => {
      shouldReconnectRef.current = false;
      reconnectAttempts.current = 0;
      cleanup();
    };
  }, [token, connect, cleanup]);

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
