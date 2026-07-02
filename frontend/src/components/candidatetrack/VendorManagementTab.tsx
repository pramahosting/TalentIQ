import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2, UploadCloud } from "lucide-react";
import { candidateTrackApi } from "../../lib/api";
import DataTable from "../DataTable";

function VendorFormModal({ initial, onClose, onSaved }: { initial?: any; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial?.name || "");
  const [location, setLocation] = useState(initial?.location || "");
  const [email, setEmail] = useState(initial?.contact_email || "");
  const [phone, setPhone] = useState(initial?.contact_phone || "");
  const [areaOfCoverage, setAreaOfCoverage] = useState(initial?.area_of_coverage || "");
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
        name, location, contact_email: email, contact_phone: phone,
        area_of_coverage: areaOfCoverage, technical_area: technicalArea, company_details: details,
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
            <label className="tiq-label" style={{ color: "#374151" }}>Location</label>
            <input className="tiq-input" value={location} onChange={e => setLocation(e.target.value)} />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label" style={{ color: "#374151" }}>Area of Coverage</label>
            <input className="tiq-input" value={areaOfCoverage} onChange={e => setAreaOfCoverage(e.target.value)} placeholder="e.g. APAC, Remote" />
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

function BulkUploadModal({ vendor, jds, onClose, onDone }: { vendor: any; jds: any[]; onClose: () => void; onDone: () => void }) {
  const [jdId, setJdId] = useState(jds[0]?.id ?? "");
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<number | null>(null);

  const handleUpload = async () => {
    if (!jdId) { setError("Select a JD."); return; }
    if (!files || files.length === 0) { setError("Select at least one resume file."); return; }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("jd_id", String(jdId));
      form.append("vendor_id", String(vendor.id));
      for (let i = 0; i < files.length; i++) form.append("files", files[i]);
      const res = await candidateTrackApi.bulkUploadCandidates(form);
      setResult(res.created);
      onDone();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Bulk upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 460, width: "94%", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>Bulk Upload Resumes — {vendor.name}</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>×</button>
        </div>
        {result !== null ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <div style={{ fontWeight: 700, color: "var(--teal-500)", marginBottom: 10 }}>✅ {result} candidate(s) created</div>
            <button className="tiq-btn tiq-btn-primary" onClick={onClose}>Done</button>
          </div>
        ) : (
          <>
            {error && <div className="tiq-alert tiq-alert-error" style={{ marginBottom: 10 }}>{error}</div>}
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>JD *</label>
              <select className="tiq-input" value={jdId} onChange={e => setJdId(e.target.value)}>
                <option value="">Select JD…</option>
                {jds.map(j => <option key={j.id} value={j.id}>{j.jd_title}</option>)}
              </select>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>Resume Files *</label>
              <input type="file" accept=".pdf,.doc,.docx" multiple onChange={e => setFiles(e.target.files)} />
              {files && <div style={{ fontSize: 11, color: "var(--teal-500)", marginTop: 6 }}>{files.length} file(s) selected</div>}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 12 }}>
              One candidate is created per file, named from the filename. Edit afterwards in Candidate Tracking to add email/phone.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="tiq-btn tiq-btn-primary" onClick={handleUpload} disabled={uploading}>
                {uploading ? "Uploading…" : "Upload"}
              </button>
              <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function VendorManagementTab() {
  const qc = useQueryClient();
  const { data: vendors = [] } = useQuery({ queryKey: ["ct-vendors"], queryFn: candidateTrackApi.listVendors });
  const { data: jds = [] } = useQuery({ queryKey: ["ct-jds"], queryFn: candidateTrackApi.listJDs });
  const [modalState, setModalState] = useState<null | { mode: "create" } | { mode: "edit"; vendor: any }>(null);
  const [bulkUploadFor, setBulkUploadFor] = useState<any>(null);
  const [selectedIds, setSelectedIds] = useState<Array<number | string>>([]);

  const deleteMut = useMutation({
    mutationFn: (id: number) => candidateTrackApi.deleteVendor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ct-vendors"] }),
  });
  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => candidateTrackApi.bulkDeleteVendors(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ct-vendors"] }); setSelectedIds([]); },
  });

  // Email/Phone are intentionally NOT shown as table columns (decluttering
  // the main list) — they're still fully editable in the form modal.
  const rows = vendors.map((v: any) => ({
    id: v.id,
    "Vendor Name": v.name,
    "Location": v.location || "—",
    "Area of Coverage": v.area_of_coverage || "—",
    "Technical Area": v.technical_area || "—",
    "JDs Involved": v.jd_count,
    "Candidates Submitted": v.candidate_count,
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
        <button className="tiq-btn tiq-btn-primary" onClick={() => setModalState({ mode: "create" })}>
          <Plus size={14} /> New Vendor
        </button>
      </div>
      <div className="tiq-card" style={{ padding: 0 }}>
        <DataTable
          columns={["Vendor Name", "Location", "Area of Coverage", "Technical Area", "JDs Involved", "Candidates Submitted", "Created On"]}
          rows={rows}
          getRowKey={(row) => row.id}
          selectable
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          actionsLabel="Actions"
          actionsWidth={140}
          emptyMessage="No vendors yet — add one to start tracking submissions"
          renderActions={(row) => (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="tiq-btn tiq-btn-outline tiq-btn-sm" title="Bulk upload resumes" onClick={() => setBulkUploadFor(row._raw)}>
                <UploadCloud size={12} />
              </button>
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
      {bulkUploadFor && (
        <BulkUploadModal
          vendor={bulkUploadFor}
          jds={jds}
          onClose={() => setBulkUploadFor(null)}
          onDone={() => qc.invalidateQueries({ queryKey: ["ct-candidates"] })}
        />
      )}
    </div>
  );
}
