/**
 * Cross-Tab Synchronization Service for SSK ERP
 *
 * Provides instant real-time synchronization between multiple open browser tabs/windows
 * using standard HTML5 BroadcastChannel with localStorage fallback.
 */

import { useEffect, useRef } from "react";

const CHANNEL_NAME = "ssk_erp_cross_tab_sync";
const STORAGE_KEY = "ssk_erp_sync_event";

// Unique ID for this browser tab/window instance
const TAB_ID = `tab_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

let channel = null;
try {
  if (typeof window !== "undefined" && typeof window.BroadcastChannel === "function") {
    channel = new BroadcastChannel(CHANNEL_NAME);
  }
} catch (e) {
  console.warn("[CrossTabSync] BroadcastChannel not supported or restricted, using storage fallback:", e);
}

// Registry of active listeners: Map<id, { entities: string[] | "*", callback: Function }>
const listeners = new Map();
let listenerSeq = 0;

/**
 * Dispatch an event to local listeners registered in THIS window/tab
 */
function dispatchToLocalListeners(event) {
  listeners.forEach(({ entities, callback }) => {
    try {
      if (entities === "*" || entities.includes(event.entity)) {
        callback(event);
      }
    } catch (err) {
      console.error("[CrossTabSync] Error in listener callback:", err);
    }
  });
}

// Listen for incoming messages from other tabs via BroadcastChannel
if (channel) {
  channel.onmessage = (messageEvent) => {
    const data = messageEvent?.data;
    if (data && data.senderId !== TAB_ID && data.entity) {
      dispatchToLocalListeners(data);
    }
  };
}

// Listen for incoming messages from other tabs via window 'storage' event (fallback & cross-process)
if (typeof window !== "undefined") {
  window.addEventListener("storage", (storageEvent) => {
    if (storageEvent.key === STORAGE_KEY && storageEvent.newValue) {
      try {
        const data = JSON.parse(storageEvent.newValue);
        if (data && data.senderId !== TAB_ID && data.entity) {
          dispatchToLocalListeners(data);
        }
      } catch {
        // Ignore JSON parse errors
      }
    }
  });
}

/**
 * Broadcast an entity mutation event to all other open tabs.
 *
 * @param {string} entity - e.g. "styles", "sku-map", "materials", "inventory", "pos", "workers"
 * @param {Object} [meta] - optional payload like { action: "create" | "update" | "delete", data: any }
 */
export function broadcastSync(entity, meta = {}) {
  if (!entity || typeof window === "undefined") return;

  const eventPayload = {
    entity,
    action: meta.action || "mutate",
    data: meta.data || null,
    senderId: TAB_ID,
    timestamp: Date.now(),
  };

  // 1. Send via BroadcastChannel (instant in modern browsers)
  if (channel) {
    try {
      channel.postMessage(eventPayload);
    } catch (err) {
      console.warn("[CrossTabSync] Failed to postMessage via BroadcastChannel:", err);
    }
  }

  // 2. Also write to localStorage to trigger 'storage' event in other tabs (guaranteed cross-window delivery)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(eventPayload));
  } catch {
    // localStorage might fail in rare quota-exceeded or private mode situations
  }
}

/**
 * Subscribe to sync events for specific entities.
 *
 * @param {string|string[]|"*"} entities - entity name or array of entity names, or "*" for all
 * @param {Function} callback - function(event) invoked when another tab mutates the entity
 * @returns {Function} unsubscribe cleanup function
 */
export function subscribeSync(entities, callback) {
  if (typeof callback !== "function") return () => {};

  const id = ++listenerSeq;
  const entityList = entities === "*" ? "*" : Array.isArray(entities) ? entities : [entities];

  listeners.set(id, { entities: entityList, callback });

  return () => {
    listeners.delete(id);
  };
}

/**
 * React Hook: automatically subscribes to cross-tab sync events for specified entities,
 * with automatic re-validation when the tab regains focus or becomes visible.
 *
 * @param {string|string[]|"*"} entities - e.g. "styles" or ["styles", "sku-map"]
 * @param {Function} onSync - callback to run when sync occurs (usually refetch function)
 * @param {Object} [options]
 * @param {boolean} [options.refetchOnFocus=true] - whether to also re-sync when switching back to this tab
 * @param {number} [options.throttleMs=1500] - minimum milliseconds between focus refetches
 */
export function useCrossTabSync(entities, onSync, options = {}) {
  const { refetchOnFocus = true, throttleMs = 1500 } = options;
  const onSyncRef = useRef(onSync);
  onSyncRef.current = onSync;
  const lastRunRef = useRef(Date.now());

  useEffect(() => {
    if (typeof window === "undefined") return;

    // 1. Subscribe to cross-tab BroadcastChannel / storage messages
    const unsubscribe = subscribeSync(entities, (event) => {
      lastRunRef.current = Date.now();
      if (typeof onSyncRef.current === "function") {
        onSyncRef.current(event);
      }
    });

    if (!refetchOnFocus) {
      return unsubscribe;
    }

    // 2. Auto re-fetch when tab is focused / becomes visible
    const handleVisibilityOrFocus = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      const now = Date.now();
      if (now - lastRunRef.current >= throttleMs) {
        lastRunRef.current = now;
        if (typeof onSyncRef.current === "function") {
          onSyncRef.current({
            entity: Array.isArray(entities) ? entities[0] : entities,
            action: "tab_focus",
            timestamp: now,
          });
        }
      }
    };

    window.addEventListener("focus", handleVisibilityOrFocus);
    document.addEventListener("visibilitychange", handleVisibilityOrFocus);

    return () => {
      unsubscribe();
      window.removeEventListener("focus", handleVisibilityOrFocus);
      document.removeEventListener("visibilitychange", handleVisibilityOrFocus);
    };
  }, [entities, refetchOnFocus, throttleMs]);
}
