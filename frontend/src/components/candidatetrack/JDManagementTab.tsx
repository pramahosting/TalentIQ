import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2 } from "lucide-react";
import { candidateTrackApi } from "../../lib/api";
import DataTable from "../DataTable";

const JD_STATUSES = ["Open", "Shortlisting", "Interviewing", "Offer Stage", "Closed"];

function JDFormModal({ initial, clients, onClose, onSaved }: { initial?: any; clients: any[]; onClose: () => void; onSaved: () => void }) {
  const [jdTitle, setJdTitle] = useState(initial?.jd_title || "");
  const [clientId, setClientId] = useState(initial?.client_id ?? "");
  const [status, setStatus] = useState(initial?.status || "Open");
  const [description, setDescription] = useState(initial?.description || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!jdTitle.trim()) { setError("JD Title is required."); return; }
    setSaving(true);
    setError("");
    try {
      const payload: any = { jd_title: jdTitle, status, description };
      if (clientId) payload.client_id = Number(clientId);
      if (initial) await candidateTrackApi.updateJD(initial.id, payload);
      else await candidateTrackApi.createJD(payload);
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to save JD.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 480, width: "94%", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{initial ? "Edit JD" : "New JD"}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>JD Title *</label>
          <input className="tiq-input" value={jdTitle} onChange={e => setJdTitle(e.target.value)} placeholder="e.g. Senior Data Engineer" />
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Client</label>
          <select className="tiq-input" value={clientId} onChange={e => setClientId(e.target.value)}>
            <option value="">No client linked</option>
            {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {clients.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
              No clients yet — add one in the Client Management tab to link this JD.
            </div>
          )}
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Status</label>
          <select className="tiq-input" value={status} onChange={e => setStatus(e.target.value)}>
            {JD_STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Description</label>
          <textarea className="tiq-input" style={{ minHeight: 100, resize: "vertical" }} value={description} onChange={e => setDescription(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="tiq-btn tiq-btn-primary" onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function JDManagementTab() {
  const qc = useQueryClient();
  const { data: jds = [] } = useQuery({ queryKey: ["ct-jds"], queryFn: candidateTrackApi.listJDs });
  const { data: clients = [] } = useQuery({ queryKey: ["ct-clients"], queryFn: candidateTrackApi.listClients });
  const [modalState, setModalState] = useState<null | { mode: "create" } | { mode: "edit"; jd: any }>(null);
  const [selectedIds, setSelectedIds] = useState<Array<number | string>>([]);

  const deleteMut = useMutation({
    mutationFn: (id: number) => candidateTrackApi.deleteJD(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-jds"] }),
  });
  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => candidateTrackApi.bulkDeleteJDs(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ct-jds"] }); setSelectedIds([]); },
  });

  const rows = jds.map((j: any) => ({
    id: j.id,
    "JD Title": j.jd_title,
    "Client Name": j.company_name || "—",
    "Status": j.status,
    "Shortlisted": j.shortlisted_count,
    "Vendors Involved": j.vendor_count,
    "Total Candidates": j.candidate_count,
    "Created On": j.created_at ? new Date(j.created_at).toLocaleDateString() : "",
    _raw: j,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          {selectedIds.length > 0 && (
            <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
              onClick={() => { if (confirm(`Delete ${selectedIds.length} selected JD(s)? This also deletes their tracked candidates.`)) bulkDeleteMut.mutate(selectedIds as number[]); }}>
              <Trash2 size={12} /> Delete {selectedIds.length} selected
            </button>
          )}
        </div>
        <button className="tiq-btn tiq-btn-primary" onClick={() => setModalState({ mode: "create" })}>
          <Plus size={14} /> New JD
        </button>
      </div>
      <div className="tiq-card" style={{ padding: 0 }}>
        <DataTable
          columns={["JD Title", "Client Name", "Status", "Shortlisted", "Vendors Involved", "Total Candidates", "Created On"]}
          rows={rows}
          getRowKey={(row) => row.id}
          selectable
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          actionsLabel="Actions"
          emptyMessage="No JDs yet — create one to get started"
          renderActions={(row) => (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setModalState({ mode: "edit", jd: row._raw })}>
                <Edit2 size={12} />
              </button>
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                onClick={() => { if (confirm(`Delete JD "${row._raw.jd_title}"? This also deletes its tracked candidates.`)) deleteMut.mutate(row.id); }}>
                <Trash2 size={12} />
              </button>
            </div>
          )}
        />
      </div>
      {modalState && (
        <JDFormModal
          initial={modalState.mode === "edit" ? modalState.jd : undefined}
          clients={clients}
          onClose={() => setModalState(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["ct-jds"] })}
        />
      )}
    </div>
  );
}
