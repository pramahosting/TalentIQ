import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2, Upload } from "lucide-react";
import { candidateTrackApi } from "../../lib/api";
import DataTable from "../DataTable";
import CsvImportModal from "./CsvImportModal";

function VendorFormModal({ initial, onClose, onSaved }: { initial?: any; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial?.name || "");
  const [address, setAddress] = useState(initial?.address || "");
  const [email, setEmail] = useState(initial?.contact_email || "");
  const [phone, setPhone] = useState(initial?.contact_phone || "");
  const [coverageRegion, setCoverageRegion] = useState(initial?.coverage_region || "");
  const [technicalArea, setTechnicalArea] = useState(initial?.technical_area || "");
  const [details, setDetails] = useState(initial?.company_details || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!name.trim()) { setError("Vendor name is required."); return; }
    setSaving(true);
    setError("");
    try {
      const payload = {
        name, address, contact_email: email, contact_phone: phone,
        coverage_region: coverageRegion, technical_area: technicalArea, company_details: details,
      };
      if (initial) await candidateTrackApi.updateVendor(initial.id, payload);
      else await candidateTrackApi.createVendor(payload);
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to save vendor.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 520, width: "94%", maxHeight: "88vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{initial ? "Edit Vendor" : "New Vendor"}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Vendor Name *</label>
          <input className="tiq-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Talent Partners Pty Ltd" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Address</label>
            <input className="tiq-input" value={address} onChange={e => setAddress(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Coverage Region</label>
            <input className="tiq-input" value={coverageRegion} onChange={e => setCoverageRegion(e.target.value)} placeholder="e.g. APAC, Remote" />
          </div>
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Technical Area</label>
          <input className="tiq-input" value={technicalArea} onChange={e => setTechnicalArea(e.target.value)} placeholder="e.g. Data Engineering, Cloud" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Contact Email</label>
            <input className="tiq-input" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Contact Phone</label>
            <input className="tiq-input" value={phone} onChange={e => setPhone(e.target.value)} />
          </div>
        </div>
        <div className="tiq-form-group">
          <label className="tiq-label" style={{ color: "#374151" }}>Company Details</label>
          <textarea className="tiq-input" style={{ minHeight: 70, resize: "vertical" }} value={details} onChange={e => setDetails(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="tiq-btn tiq-btn-primary" onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function VendorManagementTab() {
  const qc = useQueryClient();
  const { data: vendors = [] } = useQuery({ queryKey: ["ct-vendors"], queryFn: candidateTrackApi.listVendors });
  const [modalState, setModalState] = useState<null | { mode: "create" } | { mode: "edit"; vendor: any }>(null);
  const [selectedIds, setSelectedIds] = useState<Array<number | string>>([]);
  const [csvImportOpen, setCsvImportOpen] = useState(false);

  const deleteMut = useMutation({
    mutationFn: (id: number) => candidateTrackApi.deleteVendor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-vendors"] }),
  });
  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => candidateTrackApi.bulkDeleteVendors(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ct-vendors"] }); setSelectedIds([]); },
    onError: (e: any) => alert(`Bulk delete failed: ${e.response?.data?.detail || e.message}`),
  });

  const rows = vendors.map((v: any) => ({
    id: v.id,
    "Vendor Name": v.name,
    "Address": v.address || "—",
    "Email": v.contact_email || "—",
    "Phone": v.contact_phone || "—",
    "Coverage Region": v.coverage_region || "—",
    "Technical Area": v.technical_area || "—",
    "Company Details": v.company_details || "—",
    "Created On": v.created_at ? new Date(v.created_at).toLocaleDateString() : "",
    _raw: v,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          {selectedIds.length > 0 && (
            <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
              onClick={() => { if (confirm(`Delete ${selectedIds.length} selected vendor(s)? This also deletes candidates they submitted.`)) bulkDeleteMut.mutate(selectedIds as number[]); }}>
              <Trash2 size={12} /> Delete {selectedIds.length} selected
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="tiq-btn tiq-btn-outline" onClick={() => setCsvImportOpen(true)}>
            <Upload size={14} /> Import CSV
          </button>
          <button className="tiq-btn tiq-btn-primary" onClick={() => setModalState({ mode: "create" })}>
            <Plus size={14} /> New Vendor
          </button>
        </div>
      </div>
      <div className="tiq-card" style={{ padding: 0 }}>
        <DataTable
          columns={["Vendor Name", "Address", "Email", "Phone", "Coverage Region", "Technical Area", "Company Details", "Created On"]}
          rows={rows}
          getRowKey={(row) => row.id}
          selectable
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          actionsLabel="Actions"
          emptyMessage="No vendors yet — add one to start tracking submissions"
          renderActions={(row) => (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setModalState({ mode: "edit", vendor: row._raw })}>
                <Edit2 size={12} />
              </button>
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                onClick={() => { if (confirm(`Delete vendor "${row._raw.name}"? This also deletes candidates they submitted.`)) deleteMut.mutate(row.id); }}>
                <Trash2 size={12} />
              </button>
            </div>
          )}
        />
      </div>
      {modalState && (
        <VendorFormModal
          initial={modalState.mode === "edit" ? modalState.vendor : undefined}
          onClose={() => setModalState(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["ct-vendors"] })}
        />
      )}
      {csvImportOpen && (
        <CsvImportModal
          title="Vendors"
          columns={["name", "address", "contact_email", "contact_phone", "coverage_region", "technical_area", "company_details"]}
          sampleRow={["Talent Partners Pty Ltd", "Sydney NSW", "contact@talentpartners.com", "0400000000", "APAC", "Data Engineering", "Boutique recruitment agency"]}
          onImport={candidateTrackApi.importVendorsCsv}
          onClose={() => setCsvImportOpen(false)}
          onDone={() => qc.invalidateQueries({ queryKey: ["ct-vendors"] })}
        />
      )}
    </div>
  );
}
