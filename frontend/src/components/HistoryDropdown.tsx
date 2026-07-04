import { useState, useRef, useEffect } from "react";
import { ChevronDown, Trash2 } from "lucide-react";

export interface HistoryDropdownOption {
  id: number | string;
  label: string;
}

interface HistoryDropdownProps {
  value: number | string | null;
  onChange: (id: number | string | null) => void;
  options: HistoryDropdownOption[];
  onDelete: (id: number | string) => void;
  placeholder?: string;
  confirmDeleteMessage?: string;
}

/**
 * A <select>-styled dropdown where every option row has its own delete
 * (trash) button at the end. Native <select>/<option> elements can't host
 * interactive children, so this is a custom listbox built from plain divs
 * — same look, same click-to-open/select behavior, just with a working
 * delete affordance per row.
 */
export default function HistoryDropdown({
  value, onChange, options, onDelete, placeholder = "Select…", confirmDeleteMessage = "Delete this item?",
}: HistoryDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", esc);
    };
  }, []);

  const selected = options.find(o => String(o.id) === String(value));

  const handleDelete = (e: React.MouseEvent, id: number | string) => {
    e.stopPropagation();
    if (confirm(confirmDeleteMessage)) {
      onDelete(id);
      if (String(id) === String(value)) onChange(null);
    }
  };

  return (
    <div ref={ref} style={{ position: "relative", flex: 1, width: "100%" }}>
      <button
        type="button"
        className="tiq-input"
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", minHeight: 38, height: "auto", display: "flex", alignItems: "center",
          justifyContent: "space-between", gap: 8, cursor: "pointer", textAlign: "left",
          background: "var(--bg-card, #fff)", boxSizing: "border-box", padding: "8px 12px",
        }}
      >
        <span style={{
          whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.35,
          color: selected ? "inherit" : "var(--text-muted)",
        }}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown size={14} style={{ flexShrink: 0, opacity: .6 }} />
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 200,
          background: "#ffffff", color: "#111827", border: "1px solid #e5e7eb", borderRadius: 8,
          boxShadow: "0 8px 28px rgba(0,0,0,.16)", maxHeight: 280, overflowY: "auto",
        }}>
          {options.length === 0 ? (
            <div style={{ padding: "10px 12px", fontSize: 12, color: "#9ca3af" }}>No items yet</div>
          ) : options.map(opt => (
            <div
              key={opt.id}
              onMouseDown={e => {
                // mousedown (not click) so this fires and commits the
                // selection deterministically, before the document-level
                // outside-click listener (also mousedown-based) or any
                // blur/focus side effects from the trigger button can race
                // with it and swallow the selection.
                e.preventDefault();
                onChange(opt.id);
                setOpen(false);
              }}
              style={{
                display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8,
                padding: "8px 10px", cursor: "pointer", fontSize: 13,
                background: String(opt.id) === String(value) ? "rgba(13,148,136,.08)" : undefined,
                borderBottom: "1px solid #f3f4f6",
              }}
              onMouseEnter={e => { if (String(opt.id) !== String(value)) e.currentTarget.style.background = "#f9fafb"; }}
              onMouseLeave={e => { if (String(opt.id) !== String(value)) e.currentTarget.style.background = ""; }}
            >
              <span style={{ whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.35, flex: 1 }}>
                {opt.label}
              </span>
              <span
                onMouseDown={e => { e.preventDefault(); e.stopPropagation(); handleDelete(e, opt.id); }}
                style={{ color: "#9ca3af", cursor: "pointer", display: "flex", flexShrink: 0, padding: 2 }}
                title="Delete"
              >
                <Trash2 size={13} />
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}