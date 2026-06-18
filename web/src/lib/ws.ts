import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";

export type WsEvent =
  | { type: "hello" }
  | { type: "transaction.new"; transaction: Record<string, unknown> }
  | { type: "transaction.updated"; transaction: Record<string, unknown> }
  | { type: "transaction.deleted"; id: number }
  | { type: "account.new" | "account.updated"; account: Record<string, unknown> }
  | { type: "category.new" | "category.updated"; category: Record<string, unknown> }
  | { type: "account_type.new"; account_type: Record<string, unknown> }
  | { type: "account_type.deleted"; id: number };

export function useEventStream(token?: string) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryDelay = 1000;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(wsUrl(token));
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        retryDelay = 1000;
      };
      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          retryTimer = setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 30_000);
        }
      };
      ws.onmessage = (e) => {
        try {
          setLastEvent(JSON.parse(e.data) as WsEvent);
        } catch {
          // ignore
        }
      };
      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [token]);

  return { connected, lastEvent };
}
