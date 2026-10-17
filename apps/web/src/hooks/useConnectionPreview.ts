import { useEffect, useState } from "react";
import { projectApi } from "@/apis/projects";
import type { Drawing, WiringRow } from "@/apis/types";
import { previewConnectionKey } from "@/apis/drawing-evidence";

interface Preview { key: string; source: Drawing | null; target: Drawing | null; error: string; targetError: string }
export function useConnectionPreview(enabled: boolean, sourceId: string | undefined, row: WiringRow | null, showTarget: boolean, retry: number) {
  const [value, setValue] = useState<Preview | null>(null);
  const rowId = row?.id; const version = row?.recordVersion;
  const key = `${sourceId}:${previewConnectionKey(row)}:${showTarget}:${retry}`;
  useEffect(() => {
    if (!enabled || !sourceId) return;
    const abort = new AbortController();
    const target = showTarget && row ? projectApi.target(row, abort.signal) : Promise.resolve(null);
    void Promise.allSettled([projectApi.drawing(sourceId, abort.signal), target]).then(([source, destination]) => {
      if (abort.signal.aborted) return;
      setValue({ key, source: source.status === "fulfilled" ? source.value : null,
        target: destination.status === "fulfilled" ? destination.value : null,
        error: source.status === "rejected" ? String(source.reason) : "",
        targetError: destination.status === "rejected" ? String(destination.reason) : "" });
    });
    return () => abort.abort();
    // key includes selection identity/version; the selected row is refreshed from current table data.
  }, [enabled, sourceId, row, rowId, version, showTarget, retry, key]);
  return value?.key === key ? { ...value, loading: false } : { source: null, target: null, error: "", targetError: "", loading: enabled && !!sourceId };
}
