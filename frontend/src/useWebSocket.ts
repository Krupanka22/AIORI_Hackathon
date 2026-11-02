import { useEffect, useRef, useCallback, useState } from 'react';

export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

type Listener = (msg: WSMessage) => void;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Set<Listener>>(new Set());
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}://${host}/ws/live`);

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ type: 'ping' }));
    };

    ws.onmessage = (ev) => {
      try {
        const msg: WSMessage = JSON.parse(ev.data);
        listenersRef.current.forEach((fn) => fn(msg));
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback((fn: Listener) => {
    listenersRef.current.add(fn);
    return () => { listenersRef.current.delete(fn); };
  }, []);

  return { connected, subscribe };
}
