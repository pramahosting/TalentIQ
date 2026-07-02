import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2 } from "lucide-react";
import { candidateTrackApi } from "../../lib/api";
import DataTable from "../DataTable";

function ClientFormModal({ initial, onClose, onSaved }: { initial?: any; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial?.name || "");
  const [location, setLocation] = useState(initial?.location || "");
  const [abn, setAbn] = useState(initial?.abn || "");
  const [partnershipFrom, setPartnershipFrom] = useState(initial?.partnership_from || "");
  const [areaOfWork, setAreaOfWork] = useState(initial?.area_of_work || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!name.trim()) { setError("Client name is required."); return; }
    setSaving(true);
    setError("");
    try {
      const payload = { name, location, abn, partnership_from: partnershipFrom || null, area_of_work: areaOfWork };
      if (initial) await candidateTrackApi.updateClient(initial.id, payload);
      else await candidateTrackApi.createClient(payload);
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to save client.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 480, width: "94%", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{initial ? "Edit Client" : "New Client"}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Client / Company Name *</label>
          <input className="tiq-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Commonwealth Bank of Australia" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Location</label>
            <input className="tiq-input" value={location} onChange={e => setLocation(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>ABN</label>
            <input className="tiq-input" value={abn} onChange={e => setAbn(e.target.value)} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Partnership From</label>
            <input type="date" className="tiq-input" value={partnershipFrom} onChange={e => setPartnershipFrom(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Area of Work</label>
            <input className="tiq-input" value={areaOfWork} onChange={e => setAreaOfWork(e.target.value)} placeholder="e.g. Banking, Insurance" />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="tiq-btn tiq-btn-primary" onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function ClientManagementTab() {
  const qc = useQueryClient();
  const { data: clients = [] } = useQuery({ queryKey: ["ct-clients"], queryFn: candidateTrackApi.listClients });
  const [modalState, setModalState] = useState<null | { mode: "create" } | { mode: "edit"; client: any }>(null);
  const [selectedIds, setSelectedIds] = useState<Array<number | string>>([]);

  const deleteMut = useMutation({
    mutationFn: (id: number) => candidateTrackApi.deleteClient(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-clients"] }),
  });
  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => candidateTrackApi.bulkDeleteClients(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ct-clients"] }); setSelectedIds([]); },
  });

  const rows = clients.map((c: any) => ({
    id: c.id,
    "Name": c.name,
    "Location": c.location || "—",
    "ABN": c.abn || "—",
    "Partnership From": c.partnership_from || "—",
    "Area of Work": c.area_of_work || "—",
    "Linked JDs": c.jd_count,
    "Created": c.created_at ? new Date(c.created_at).toLocaleDateString() : "",
    _raw: c,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          {selectedIds.length > 0 && (
            <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
              onClick={() => { if (confirm(`Delete ${selectedIds.length} selected client(s)?`)) bulkDeleteMut.mutate(selectedIds as number[]); }}>
              <Trash2 size={12} /> Delete {selectedIds.length} selected
            </button>
          )}
        </div>
        <button className="tiq-btn tiq-btn-primary" onClick={() => setModalState({ mode: "create" })}>
          <Plus size={14} /> New Client
        </button>
      </div>
      <div className="tiq-card" style={{ padding: 0 }}>
        <DataTable
          columns={["Name", "Location", "ABN", "Partnership From", "Area of Work", "Linked JDs", "Created"]}
          rows={rows}
          getRowKey={(row) => row.id}
          selectable
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          actionsLabel="Actions"
          emptyMessage="No clients yet — add one to link JDs to it"
          renderActions={(row) => (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setModalState({ mode: "edit", client: row._raw })}>
                <Edit2 size={12} />
              </button>
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                onClick={() => { if (confirm(`Delete client "${row._raw.name}"?`)) deleteMut.mutate(row.id); }}>
                <Trash2 size={12} />
              </button>
            </div>
          )}
        />
      </div>
      {modalState && (
        <ClientFormModal
          initial={modalState.mode === "edit" ? modalState.client : undefined}
          onClose={() => setModalState(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["ct-clients"] })}
        />
      )}
    </div>
  );
}
