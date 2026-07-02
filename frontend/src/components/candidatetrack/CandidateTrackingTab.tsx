import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2, AlertTriangle, Download, History } from "lucide-react";
import { candidateTrackApi, api } from "../../lib/api";
import DataTable from "../DataTable";

const CANDIDATE_STATUSES = [
  "Applied", "Shortlisted", "Interview Scheduled", "Interview Completed",
  "Selected", "Offered", "Rejected",
];

async function openBlobInNewTab(url: string) {
  try {
    const res = await api.get(url, { responseType: "blob" });
    const objectUrl = URL.createObjectURL(res.data);
    window.open(objectUrl, "_blank");
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch {
    alert("Could not load the file.");
  }
}

function CandidateFormModal({
  initial, jds, vendors, onClose, onSaved,
}: { initial?: any; jds: any[]; vendors: any[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial?.name || "");
  const [email, setEmail] = useState(initial?.email || "");
  const [phone, setPhone] = useState(initial?.phone || "");
  const [jdId, setJdId] = useState(initial?.jd_id ?? jds[0]?.id ?? "");
  const [vendorId, setVendorId] = useState(initial?.vendor_id ?? vendors[0]?.id ?? "");
  const [status, setStatus] = useState(initial?.status || "Applied");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [duplicateWarning, setDuplicateWarning] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) { setError("Candidate name is required."); return; }
    if (!jdId) { setError("Select a JD."); return; }
    if (!vendorId) { setError("Select a vendor."); return; }
    setSaving(true);
    setError("");
    try {
      if (initial) {
        await candidateTrackApi.updateCandidate(initial.id, {
          name, email, phone, jd_id: Number(jdId), vendor_id: Number(vendorId), status,
        });
      } else {
        const form = new FormData();
        form.append("jd_id", String(jdId));
        form.append("vendor_id", String(vendorId));
        form.append("name", name);
        form.append("email", email);
        form.append("phone", phone);
        form.append("status", status);
        if (file) form.append("file", file);
        const result = await candidateTrackApi.createCandidate(form);
        if (result.is_duplicate) setDuplicateWarning(true);
      }
      onSaved();
      if (!duplicateWarning) onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to save candidate.");
    } finally {
      setSaving(false);
    }
  };

  if (duplicateWarning) {
    return (
      <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 420, width: "94%", textAlign: "center" }}>
          <AlertTriangle size={32} color="#f59e0b" style={{ margin: "0 auto 12px" }} />
          <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 8 }}>Duplicate candidate detected</div>
          <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
            A candidate with this email or phone was already submitted for this JD by another (or the same) vendor.
            This submission was saved and flagged as a duplicate — the original stays as the primary record, and this one is kept for vendor audit purposes.
          </p>
          <button className="tiq-btn tiq-btn-primary" onClick={onClose}>OK</button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 520, width: "94%", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{initial ? "Edit Candidate" : "New Candidate"}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Candidate Name *</label>
          <input className="tiq-input" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Email</label>
            <input className="tiq-input" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Phone</label>
            <input className="tiq-input" value={phone} onChange={e => setPhone(e.target.value)} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>JD *</label>
            <select className="tiq-input" value={jdId} onChange={e => setJdId(e.target.value)}>
              <option value="">Select JD…</option>
              {jds.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Vendor *</label>
            <select className="tiq-input" value={vendorId} onChange={e => setVendorId(e.target.value)}>
              <option value="">Select vendor…</option>
              {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Status</label>
          <select className="tiq-input" value={status} onChange={e => setStatus(e.target.value)}>
            {CANDIDATE_STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        {!initial && (
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Resume File</label>
            <input type="file" accept=".pdf,.doc,.docx" onChange={e => setFile(e.target.files?.[0] || null)} />
          </div>
        )}
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="tiq-btn tiq-btn-primary" onClick={handleSave} disabled={saving || !jds.length || !vendors.length}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
        </div>
        {(!jds.length || !vendors.length) && (
          <div style={{ fontSize: 11, color: "#f59e0b", marginTop: 8 }}>
            Create at least one JD and one Vendor first.
          </div>
        )}
      </div>
    </div>
  );
}

function StatusHistoryModal({ candidateId, candidateName, onClose }: { candidateId: number; candidateName: string; onClose: () => void }) {
  const { data: log = [] } = useQuery({
    queryKey: ["ct-candidate-log", candidateId],
    queryFn: () => candidateTrackApi.candidateStatusLog(candidateId),
  });
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 440, width: "94%", maxHeight: "80vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>Status History — {candidateName}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {log.length === 0 ? (
          <div style={{ fontSize: 13, color: "#6b7280" }}>No status changes recorded yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {log.map((entry: any) => (
              <div key={entry.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 13 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#0d9488", marginTop: 5, flexShrink: 0 }} />
                <div>
                  <div>
                    {entry.old_status ? <><span style={{ color: "#9ca3af" }}>{entry.old_status}</span> → </> : null}
                    <strong>{entry.new_status}</strong>
                  </div>
                  <div style={{ fontSize: 11, color: "#9ca3af" }}>{entry.changed_at ? new Date(entry.changed_at).toLocaleString() : ""}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CandidateTrackingTab() {
  const qc = useQueryClient();
  const { data: candidates = [] } = useQuery({ queryKey: ["ct-candidates"], queryFn: candidateTrackApi.listCandidates });
  const { data: jds = [] } = useQuery({ queryKey: ["ct-jds"], queryFn: candidateTrackApi.listJDs });
  const { data: vendors = [] } = useQuery({ queryKey: ["ct-vendors"], queryFn: candidateTrackApi.listVendors });

  const [modalState, setModalState] = useState<null | { mode: "create" } | { mode: "edit"; candidate: any }>(null);
  const [historyFor, setHistoryFor] = useState<{ id: number; name: string } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Array<number | string>>([]);

  const deleteMut = useMutation({
    mutationFn: (id: number) => candidateTrackApi.deleteCandidate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-candidates"] }),
  });

  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => candidateTrackApi.bulkDeleteCandidates(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ct-candidates"] }); setSelectedIds([]); },
  });

  const quickStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => candidateTrackApi.updateCandidate(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-candidates"] }),
  });

  const rows = candidates.map((c: any) => ({
    id: c.id,
    "Name": c.name,
    "Email": c.email || "—",
    "Phone": c.phone || "—",
    "JD": c.jd_title || "—",
    "Client / Company": c.client_name || "—",
    "Source Vendor": c.vendor_name || "—",
    "Status": c.status,
    "Submitted": c.submitted_at ? new Date(c.submitted_at).toLocaleDateString() : "",
    _raw: c,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          {selectedIds.length > 0 && (
            <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
              onClick={() => { if (confirm(`Delete ${selectedIds.length} selected candidate(s)?`)) bulkDeleteMut.mutate(selectedIds as number[]); }}>
              <Trash2 size={12} /> Delete {selectedIds.length} selected
            </button>
          )}
        </div>
        <button className="tiq-btn tiq-btn-primary" onClick={() => setModalState({ mode: "create" })}>
          <Plus size={14} /> New Candidate
        </button>
      </div>
      <div className="tiq-card" style={{ padding: 0 }}>
        <DataTable
          columns={["Name", "Email", "Phone", "JD", "Client / Company", "Source Vendor", "Status", "Submitted"]}
          rows={rows}
          getRowKey={(row) => row.id}
          selectable
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          actionsLabel="Actions"
          actionsWidth={260}
          emptyMessage="No candidates tracked yet"
          rowStyle={() => undefined}
          renderActions={(row) => (
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <select
                value={row._raw.status}
                onChange={e => quickStatusMut.mutate({ id: row.id, status: e.target.value })}
                style={{ fontSize: 11, padding: "4px 6px", borderRadius: 5, border: "1px solid var(--border)" }}
                title="Update status"
              >
                {CANDIDATE_STATUSES.map(s => <option key={s}>{s}</option>)}
              </select>
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" title="Status history"
                onClick={() => setHistoryFor({ id: row.id, name: row._raw.name })}>
                <History size={12} />
              </button>
              {row._raw.has_resume && (
                <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" title="View resume"
                  onClick={() => openBlobInNewTab(`/api/candidatetrack/candidates/${row.id}/resume`)}>
                  <Download size={12} />
                </button>
              )}
              <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setModalState({ mode: "edit", candidate: row._raw })}>
                <Edit2 size={12} />
              </button>
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                onClick={() => { if (confirm(`Delete candidate "${row._raw.name}"?`)) deleteMut.mutate(row.id); }}>
                <Trash2 size={12} />
              </button>
            </div>
          )}
        />
      </div>
      {modalState && (
        <CandidateFormModal
          initial={modalState.mode === "edit" ? modalState.candidate : undefined}
          jds={jds}
          vendors={vendors}
          onClose={() => setModalState(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["ct-candidates"] })}
        />
      )}
      {historyFor && (
        <StatusHistoryModal candidateId={historyFor.id} candidateName={historyFor.name} onClose={() => setHistoryFor(null)} />
      )}
    </div>
  );
}
