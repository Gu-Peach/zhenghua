import { useEffect, useState } from "react";
import { projectApi } from "@/apis/projects";

/** Reconnects with a cursor; every reconnect also requests a fresh business snapshot. */
export function useExtractionUpdates(id: string, active: boolean, refresh: () => void) {
  const [disconnected, setDisconnected] = useState(false);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const changed = () => { if (!timer) timer = setTimeout(() => { timer = undefined; refresh(); }, 300); };
    void projectApi.watchExtraction(id, controller.signal, changed, setDisconnected);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [id, active, refresh]);
  return disconnected;
}
