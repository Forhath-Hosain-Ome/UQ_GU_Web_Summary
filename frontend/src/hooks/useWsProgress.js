import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "../store/authStore";

/**
 * useBatchSocket(batchId, { onProgress, onComplete, onError })
 * Opens a WS connection to /ws/batches/<batchId>/progress/?token=<jwt>
 * Calls the appropriate callback on each message.
 * Automatically closes when batchId changes or component unmounts.
 */
export function useWsProgress(batchId, { onProgress, onComplete, onError } = {}) {
  const wsRef    = useRef(null);
  const timerRef = useRef(null);

  const connect = useCallback(() => {
    if (!batchId) return;
    const token = useAuthStore.getState().access;
    if (!token)  return;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url   = `${proto}://${window.location.host}/ws/batches/${batchId}/progress/?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Clear any reconnect timer
      if (timerRef.current) clearTimeout(timerRef.current);
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }

      if (msg.event === "progress") onProgress?.(msg);
      if (msg.event === "complete") {
        onComplete?.(msg);
        ws.close(1000); // clean close — no more updates expected
      }
      if (msg.event === "error") onError?.(msg);
    };

    ws.onclose = (e) => {
      // Reconnect unless intentional close (1000) or batch is done
      if (e.code !== 1000 && e.code !== 4401 && e.code !== 4404) {
        timerRef.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => ws.close();
  }, [batchId, onProgress, onComplete, onError]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close(1000);
    };
  }, [connect]);
}
