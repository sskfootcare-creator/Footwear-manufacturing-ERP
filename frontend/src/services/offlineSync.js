/**
 * Offline Sync Service (U-010)
 * Provides local caching and automatic sync-on-reconnect for warehouse floor operations.
 */

const STORAGE_KEY = "SSK_WAREHOUSE_OFFLINE_QUEUE";

export function getOfflineQueue() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.warn("Failed to read offline queue:", e);
    return [];
  }
}

export function saveOfflineQueue(queue) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
  } catch (e) {
    console.warn("Failed to save offline queue:", e);
  }
}

export function queueOfflineAction(actionType, payload) {
  const queue = getOfflineQueue();
  const entry = {
    id: `offline_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    type: actionType,
    payload,
    timestamp: new Date().toISOString(),
  };
  queue.push(entry);
  saveOfflineQueue(queue);
  window.dispatchEvent(new CustomEvent("ssk_offline_queue_updated", { detail: { count: queue.length } }));
  return entry;
}

export async function flushOfflineQueue() {
  const queue = getOfflineQueue();
  if (queue.length === 0) return { synced: 0, failed: 0 };

  try {
    const res = await fetch("/api/sync/offline-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operations: queue }),
    });

    if (res.ok) {
      const data = await res.json();
      // Clear successfully synced items
      const failedIds = new Set((data.results || []).filter((r) => r.status === "failed").map((r) => r.id));
      const remaining = queue.filter((item) => failedIds.has(item.id));
      saveOfflineQueue(remaining);
      window.dispatchEvent(new CustomEvent("ssk_offline_queue_updated", { detail: { count: remaining.length } }));
      return data;
    }
  } catch (err) {
    console.warn("Offline flush failed; will retry on next reconnect", err);
  }
  return { synced: 0, failed: queue.length };
}

// Global online event listener
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    console.log("Device reconnected to network. Flushing offline queue...");
    flushOfflineQueue();
  });
}
