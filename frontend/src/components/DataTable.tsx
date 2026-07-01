import { useState, useRef, useEffect, useMemo, ReactNode } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown, RotateCcw, Filter, Search, X } from "lucide-react";

const DEFAULT_COL_WIDTH = 170;
const MIN_COL_WIDTH = 80;
const ACTIONS_COL_WIDTH = 110;

function cellString(value: any): string {
  if (value === null || value === undefined || value === "") return "(Blank)";
  if (typeof value === "object") return "[JSON]";
  return String(value);
}

function renderCellDisplay(value: any): ReactNode {
  if (value === null || value === undefined) return <span style={{ color: "var(--text-muted)" }}>null</span>;
  if (typeof value === "object") return <span style={{ color: "var(--teal-500)", fontSize: 11 }}>[JSON]</span>;
  const s = String(value);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
}

// Small borderless popover anchored to whatever triggered it (the filter
// icon), closes on outside click — same pattern as the Excel autofilter.
function FilterPopover({ x, y, width = 240, onClose, children }: { x: number; y: number; width?: number; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  const clampedX = Math.max(8, Math.min(x, window.innerWidth - width - 12));

  return (
    <div ref={ref} style={{
      position: "fixed", left: clampedX, top: y, zIndex: 1500, width,
      background: "#ffffff", color: "#111827", border: "1px solid #e5e7eb",
      borderRadius: 10, boxShadow: "0 8px 28px rgba(0,0,0,.18)", overflow: "hidden",
    }}>
      {children}
    </div>
  );
}

interface DataTableProps {
  columns: string[];
  rows: any[];
  getRowKey: (row: any, idx: number) => string | number;
  rowStyle?: (row: any) => React.CSSProperties | undefined;
  actionsLabel?: string;                      // e.g. "Actions" — omit to hide the actions column
  renderActions?: (row: any) => ReactNode;
  defaultColWidth?: number;
  emptyMessage?: string;
}

/**
 * Generic data grid: drag-to-resize columns, click-to-sort headers, an
 * Excel-style per-column filter dropdown (funnel icon next to the sort
 * arrow), a global search box above the table, and a contextual "Reset
 * Columns" button that appears centered above the table once you've
 * actually resized something.
 */
export default function DataTable({
  columns, rows, getRowKey, rowStyle, actionsLabel, renderActions,
  defaultColWidth = DEFAULT_COL_WIDTH, emptyMessage = "No records",
}: DataTableProps) {
  const [widths, setWidths] = useState<Record<string, number>>({});
  const [resizingCol, setResizingCol] = useState<string | null>(null);
  const [sort, setSort] = useState<{ col: string; dir: "asc" | "desc" } | null>(null);
  const [colFilters, setColFilters] = useState<Record<string, Set<string>>>({});
  const [search, setSearch] = useState("");
  const [openFilter, setOpenFilter] = useState<{ col: string; x: number; y: number } | null>(null);
  const [filterSearch, setFilterSearch] = useState("");
  const [cellPopup, setCellPopup] = useState<{ x: number; y: number; text: string } | null>(null);
  const columnsKey = columns.join("|");

  // Reset all interaction state whenever the column set itself changes
  // (i.e. the caller switched to a different table) — stale widths/sorts/
  // filters from a previous table's different columns would be meaningless.
  useEffect(() => {
    setWidths({});
    setSort(null);
    setColFilters({});
    setSearch("");
    setOpenFilter(null);
    setCellPopup(null);
  }, [columnsKey]);

  const resizingRef = useRef<{ col: string; startX: number; startWidth: number } | null>(null);

  const startResize = (col: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizingRef.current = { col, startX: e.clientX, startWidth: widths[col] || defaultColWidth };
    setResizingCol(col);

    const onMove = (ev: MouseEvent) => {
      const r = resizingRef.current;
      if (!r) return;
      const next = Math.max(MIN_COL_WIDTH, r.startWidth + (ev.clientX - r.startX));
      setWidths(w => ({ ...w, [r.col]: next }));
    };
    const onUp = () => {
      resizingRef.current = null;
      setResizingCol(null);
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const toggleSort = (col: string) => {
    setSort(prev => {
      if (!prev || prev.col !== col) return { col, dir: "asc" };
      if (prev.dir === "asc") return { col, dir: "desc" };
      return null; // third click clears sort
    });
  };

  // Unique values per column, for the Excel-style filter dropdown.
  const uniqueValuesByCol = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const c of columns) {
      const set = new Set<string>();
      for (const row of rows) set.add(cellString(row[c]));
      map[c] = Array.from(set).sort((a, b) => a.localeCompare(b));
    }
    return map;
  }, [rows, columnsKey]);

  const getSelectedSet = (col: string): Set<string> =>
    colFilters[col] ?? new Set(uniqueValuesByCol[col] || []);

  const toggleFilterValue = (col: string, val: string) => {
    setColFilters(prev => {
      const base = new Set(prev[col] ?? uniqueValuesByCol[col] ?? []);
      if (base.has(val)) base.delete(val); else base.add(val);
      const next = { ...prev };
      if (base.size === (uniqueValuesByCol[col]?.length ?? 0)) {
        delete next[col]; // everything selected again == no filter
      } else {
        next[col] = base;
      }
      return next;
    });
  };

  const selectAllValues = (col: string) => setColFilters(prev => { const n = { ...prev }; delete n[col]; return n; });
  const clearAllValues  = (col: string) => setColFilters(prev => ({ ...prev, [col]: new Set() }));

  const hasCustomWidths = Object.keys(widths).length > 0;
  const activeFilterCols = Object.keys(colFilters);

  const displayRows = useMemo(() => {
    let out = rows;

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      out = out.filter(row => columns.some(c => cellString(row[c]).toLowerCase().includes(q)));
    }

    for (const col of activeFilterCols) {
      const set = colFilters[col];
      out = out.filter(row => set.has(cellString(row[col])));
    }

    if (sort) {
      const { col, dir } = sort;
      out = [...out].sort((a, b) => {
        const av = a[col], bv = b[col];
        if (av === null || av === undefined) return 1;
        if (bv === null || bv === undefined) return -1;
        const an = Number(av), bn = Number(bv);
        let cmp: number;
        if (!isNaN(an) && !isNaN(bn) && av !== "" && bv !== "") {
          cmp = an - bn;
        } else {
          cmp = String(av).localeCompare(String(bv));
        }
        return dir === "asc" ? cmp : -cmp;
      });
    }

    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, search, colFilters, sort, columnsKey]);

  const openFilterFor = (col: string) => (e: React.MouseEvent) => {
    e.stopPropagation(); // don't also trigger sort
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setFilterSearch("");
    setOpenFilter(prev => (prev?.col === col ? null : { col, x: rect.left, y: rect.bottom + 6 }));
  };

  const filterValuesForOpen = openFilter
    ? (uniqueValuesByCol[openFilter.col] || []).filter(v => v.toLowerCase().includes(filterSearch.toLowerCase()))
    : [];

  // A cell is considered truncated using the same rule renderCellDisplay
  // uses to decide whether to add the ellipsis — that's exactly when the
  // full value isn't visible and a "show full value" affordance is useful.
  const isCellTruncated = (value: any) => {
    if (value === null || value === undefined) return false;
    if (typeof value === "object") return true;
    return String(value).length > 60;
  };
  const fullCellText = (value: any) =>
    typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);

  return (
    <div>
      {/* Toolbar: global search on the left, contextual Reset Columns centered */}
      <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderBottom: "1px solid var(--border)", gap: 12 }}>
        <div style={{ position: "relative", maxWidth: 280, flex: "0 1 280px" }}>
          <Search size={13} style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search table…"
            className="tiq-input"
            style={{ paddingLeft: 28, fontSize: 12, height: 32 }}
          />
          {search && (
            <X size={13} onClick={() => setSearch("")}
              style={{ position: "absolute", right: 9, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", cursor: "pointer" }} />
          )}
        </div>

        {hasCustomWidths && (
          <button
            className="tiq-btn tiq-btn-outline tiq-btn-sm"
            onClick={() => setWidths({})}
            style={{ position: "absolute", left: "50%", transform: "translateX(-50%)" }}
            title="Reset column widths to default"
          >
            <RotateCcw size={12} /> Reset Columns
          </button>
        )}

        <div style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
          {displayRows.length}{displayRows.length !== rows.length ? ` / ${rows.length}` : ""} rows
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="tiq-table" style={{ tableLayout: "fixed", width: "100%", minWidth: columns.length * defaultColWidth }}>
          <colgroup>
            {columns.map(c => (
              <col key={c} style={{ width: (widths[c] || defaultColWidth) + "px" }} />
            ))}
            {actionsLabel && <col style={{ width: ACTIONS_COL_WIDTH + "px" }} />}
          </colgroup>
          <thead>
            <tr>
              {columns.map(c => {
                const filterActive = colFilters[c] !== undefined;
                return (
                  <th key={c} style={{ position: "relative", userSelect: "none", padding: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4, padding: "8px 6px 8px 10px", overflow: "hidden" }}>
                      <span
                        onClick={() => toggleSort(c)}
                        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "pointer", flex: 1 }}
                        title="Click to sort"
                      >
                        {c}
                      </span>
                      <span
                        onClick={() => toggleSort(c)}
                        style={{ cursor: "pointer", display: "flex", flexShrink: 0 }}
                        title="Click to sort"
                      >
                        {sort?.col === c
                          ? (sort.dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)
                          : <ChevronsUpDown size={11} style={{ opacity: .35 }} />}
                      </span>
                      <span
                        onClick={openFilterFor(c)}
                        style={{ cursor: "pointer", display: "flex", flexShrink: 0, color: filterActive ? "var(--teal-500)" : "inherit", opacity: filterActive ? 1 : .45 }}
                        title="Filter this column"
                      >
                        <Filter size={12} />
                      </span>
                    </div>
                    {/* Resize handle — visible light bar, teal on hover/drag */}
                    <span
                      onMouseDown={startResize(c)}
                      className={`tiq-col-resize-handle${resizingCol === c ? " tiq-resizing" : ""}`}
                    />
                  </th>
                );
              })}
              {actionsLabel && <th>{actionsLabel}</th>}
            </tr>
          </thead>
          <tbody>
            {displayRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (actionsLabel ? 1 : 0)} style={{ textAlign: "center", padding: 32, color: "var(--text-muted)" }}>
                  {emptyMessage}
                </td>
              </tr>
            ) : displayRows.map((row, i) => (
              <tr key={getRowKey(row, i)} style={rowStyle?.(row)}>
                {columns.map(c => {
                  const truncated = isCellTruncated(row[c]);
                  return (
                    <td
                      key={c}
                      onClick={truncated ? (e) => {
                        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                        setCellPopup({ x: rect.left, y: rect.bottom + 4, text: fullCellText(row[c]) });
                      } : undefined}
                      style={{
                        fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        cursor: truncated ? "pointer" : "default",
                      }}
                      title={truncated ? "Click to view full value" : undefined}
                    >
                      {renderCellDisplay(row[c])}
                    </td>
                  );
                })}
                {actionsLabel && <td>{renderActions?.(row)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openFilter && (
        <FilterPopover x={openFilter.x} y={openFilter.y} onClose={() => setOpenFilter(null)}>
          <div style={{ padding: 10, borderBottom: "1px solid #e5e7eb" }}>
            <input
              autoFocus
              value={filterSearch}
              onChange={e => setFilterSearch(e.target.value)}
              placeholder="Search values…"
              style={{ width: "100%", fontSize: 12, padding: "6px 8px", borderRadius: 6, border: "1px solid #e5e7eb", outline: "none", boxSizing: "border-box" }}
            />
          </div>
          <div style={{ display: "flex", gap: 6, padding: "8px 10px", borderBottom: "1px solid #e5e7eb" }}>
            <button onClick={() => selectAllValues(openFilter.col)}
              style={{ fontSize: 11, background: "none", border: "none", color: "var(--teal-500)", cursor: "pointer", padding: 0 }}>
              Select All
            </button>
            <button onClick={() => clearAllValues(openFilter.col)}
              style={{ fontSize: 11, background: "none", border: "none", color: "var(--rose-500)", cursor: "pointer", padding: 0 }}>
              Clear
            </button>
          </div>
          <div style={{ maxHeight: 220, overflowY: "auto", padding: "4px 10px" }}>
            {filterValuesForOpen.length === 0 ? (
              <div style={{ fontSize: 11, color: "#9ca3af", padding: "8px 0" }}>No matching values</div>
            ) : filterValuesForOpen.map(v => {
              const selected = getSelectedSet(openFilter.col).has(v);
              return (
                <label key={v} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12, cursor: "pointer" }}>
                  <input type="checkbox" checked={selected} onChange={() => toggleFilterValue(openFilter.col, v)} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v}</span>
                </label>
              );
            })}
          </div>
          <div style={{ padding: 10, borderTop: "1px solid #e5e7eb", textAlign: "right" }}>
            <button className="tiq-btn tiq-btn-primary tiq-btn-sm" onClick={() => setOpenFilter(null)}>Done</button>
          </div>
        </FilterPopover>
      )}

      {cellPopup && (
        <FilterPopover x={cellPopup.x} y={cellPopup.y} width={420} onClose={() => setCellPopup(null)}>
          <div style={{
            padding: 12, maxHeight: 320, overflowY: "auto", fontSize: 12,
            whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.6,
          }}>
            {cellPopup.text}
          </div>
        </FilterPopover>
      )}
    </div>
  );
}