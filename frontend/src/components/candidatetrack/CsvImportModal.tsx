import { useState } from "react";

interface CsvImportModalProps {
  title: string;
  columns: string[];           // exact expected CSV headers, in order
  sampleRow: string[];         // one example row matching `columns`, for the template download
  onImport: (form: FormData) => Promise<{ created: number; skipped: number; errors: string[] }>;
  onClose: () => void;
  onDone: () => void;
}

export default function CsvImportModal({ title, columns, sampleRow, onImport, onClose, onDone }: CsvImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null);

  const downloadTemplate = () => {
    const csv = [columns.join(","), sampleRow.join(",")].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.toLowerCase().replace(/\s+/g, "_")}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleUpload = async () => {
    if (!file) { setError("Select a CSV file first."); return; }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await onImport(form);
      setResult(res);
      onDone();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Import failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 480, width: "94%", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>Import {title} from CSV</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>

        {result ? (
          <div>
            <div style={{ fontWeight: 700, color: "var(--teal-500)", marginBottom: 6 }}>✅ {result.created} created</div>
            {result.skipped > 0 && <div style={{ fontWeight: 600, color: "#f59e0b", marginBottom: 6 }}>⚠ {result.skipped} skipped</div>}
            {result.errors.length > 0 && (
              <div style={{ background: "#fef3c7", borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 160, overflowY: "auto", marginBottom: 12 }}>
                {result.errors.map((e, i) => <div key={i} style={{ marginBottom: 3 }}>{e}</div>)}
              </div>
            )}
            <button className="tiq-btn tiq-btn-primary" onClick={onClose}>Done</button>
          </div>
        ) : (
          <>
            {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
            <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 10 }}>
              Expected columns (first row must be the header, exact names):
            </p>
            <div style={{ background: "#f3f4f6", borderRadius: 8, padding: 10, fontSize: 11, fontFamily: "monospace", marginBottom: 10, overflowX: "auto", whiteSpace: "nowrap" }}>
              {columns.join(", ")}
            </div>
            <button type="button" onClick={downloadTemplate}
              style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 12, color: "var(--teal-500)", textDecoration: "underline", marginBottom: 16, display: "block" }}>
              Download a blank CSV template
            </button>
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>CSV File *</label>
              <input type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0] || null)} />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="tiq-btn tiq-btn-primary" onClick={handleUpload} disabled={uploading}>
                {uploading ? "Importing…" : "Import"}
              </button>
              <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
