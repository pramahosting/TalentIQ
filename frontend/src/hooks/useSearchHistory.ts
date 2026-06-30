/**
 * useSearchHistory - persists past search terms per key in localStorage
 * and provides a datalist-compatible list for autocomplete.
 */
import { useState, useCallback } from "react";

export function useSearchHistory(key: string, max = 10) {
  const storageKey = `tiq_search_${key}`;

  const load = (): string[] => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "[]");
    } catch {
      return [];
    }
  };

  const [history, setHistory] = useState<string[]>(load);

  const addEntry = useCallback((term: string) => {
    const t = term.trim();
    if (!t) return;
    setHistory(prev => {
      const next = [t, ...prev.filter(x => x !== t)].slice(0, max);
      localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
  }, [storageKey, max]);

  const clearHistory = useCallback(() => {
    localStorage.removeItem(storageKey);
    setHistory([]);
  }, [storageKey]);

  return { history, addEntry, clearHistory };
}
