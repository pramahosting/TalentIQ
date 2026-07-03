import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Database, Table, ChevronRight, Save, Trash2, Plus, Search, Play, RefreshCw, ChevronLeft, ChevronDown, ChevronUp, X } from "lucide-react";
import DataTable from "../components/DataTable";

const adminApi = {
  tables: () => api.get("/api/admin/tables").then(r => r.data),
  schema: (t: string) => api.get(`/api/admin/tables/${t}/schema`).then(r => r.data),
  rows: (t: string, page: number, search?: string) =>
    api.get(`/api/admin/tables/${t}/rows`, { params: { page, page_size: 25, search } }).then(r => r.data),
  updateRow: (t: string, id: number, data: any) => api.put(`/api/admin/tables/${t}/rows/${id}`, { data }).then(r => r.data),
  deleteRow: (t: string, id: number) => api.delete(`/api/admin/tables/${t}/rows/${id}`).then(r => r.data),
  bulkDeleteRows: (t: string, ids: number[]) => api.delete(`/api/admin/tables/${t}/rows`, { data: { ids } }).then(r => r.data),
  insertRow: (t: string, data: any) => api.post(`/api/admin/tables/${t}/rows`, { data }).then(r => r.data),
  query: (sql: string) => api.post("/api/admin/query", { sql }).then(r => r.data),
};

export default function FileManagerPage() {
  const [activeTable, setActiveTable] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [editRow, setEditRow] = useState<any>(null);
  const [newRow, setNewRow] = useState(false);
  const [newData, setNewData] = useState<any>({});
  const [sqlQuery, setSqlQuery] = useState("SELECT * FROM tiq_users LIMIT 10");
  const [sqlResult, setSqlResult] = useState<any>(null);
  const [sqlError, setSqlError] = useState("");
  const [tab, setTab] = useState<"browser"|"sql">("browser");
  const [msg, setMsg] = useState("");

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 2500); };

  const { data: tables = [] } = useQuery({ queryKey: ["admin-tables"], queryFn: adminApi.tables, refetchInterval: 30000 });

  const { data: schema = [] } = useQuery({
    queryKey: ["schema", activeTable],
    queryFn: () => adminApi.schema(activeTable!),
    enabled: !!activeTable,
  });

  const { data: rowData, refetch: refetchRows, isLoading: rowsLoading } = useQuery({
    queryKey: ["rows", activeTable, page],
    queryFn: () => adminApi.rows(activeTable!, page),
    enabled: !!activeTable,
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => adminApi.updateRow(activeTable!, id, data),
    onSuccess: () => { refetchRows(); setEditRow(null); flash("Row updated."); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => adminApi.deleteRow(activeTable!, id),
    onSuccess: () => { refetchRows(); flash("Row deleted."); },
  });

  const [selectedRowIds, setSelectedRowIds] = useState<Array<number | string>>([]);
  const bulkDeleteMut = useMutation({
    mutationFn: (ids: number[]) => adminApi.bulkDeleteRows(activeTable!, ids),
    onSuccess: (_data, ids) => { refetchRows(); setSelectedRowIds([]); flash(`Deleted ${ids.length} row(s).`); },
    onError: (e: any) => { flash(`❌ Bulk delete failed: ${e.response?.data?.detail || e.message}`); },
  });

  const insertMut = useMutation({
    mutationFn: (data: any) => adminApi.insertRow(activeTable!, data),
    onSuccess: () => { refetchRows(); setNewRow(false); setNewData({}); flash("Row inserted."); },
  });

  const runSql = async () => {
    setSqlError(""); setSqlResult(null);
    try { setSqlResult(await adminApi.query(sqlQuery)); }
    catch (e: any) { setSqlError(e.response?.data?.detail || e.message); }
  };

  const editableSchema = schema.filter((c: any) => c.column_name !== "id");
  const rows = rowData?.rows || [];
  const cols = rowData?.columns || [];
  const total = rowData?.total || 0;
  const totalPages = Math.ceil(total / 25);

  return (
    <div>
      <div className="tiq-page-header">
        <h1 className="tiq-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Database size={22} color="var(--teal-500)" /> File & Database Manager
        </h1>
        <p className="tiq-page-sub">Browse, edit and manage all TalentIQ database tables</p>
      </div>

      {msg && <div className="tiq-alert tiq-alert-success" style={{ marginBottom: 16 }}>{msg}</div>}

      <div className="tiq-tabs">
        <button className={`tiq-tab${tab==="browser"?" active":""}`} onClick={() => setTab("browser")}>
          <Table size={13} style={{display:"inline",marginRight:6}} />Table Browser
        </button>
        <button className={`tiq-tab${tab==="sql"?" active":""}`} onClick={() => setTab("sql")}>
          <Play size={13} style={{display:"inline",marginRight:6}} />SQL Query
        </button>
      </div>

      {tab === "browser" && (
        <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 20, alignItems: "flex-start" }}>
          {/* TABLE LIST */}
          <div className="tiq-card" style={{ padding: 0 }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
              Tables ({tables.length})
            </div>
            {tables.map((t: any) => (
              <div key={t.table} onClick={() => { setActiveTable(t.table); setPage(1); setEditRow(null); setNewRow(false); }}
                style={{
                  padding: "10px 16px", cursor: "pointer", fontSize: 13,
                  background: activeTable === t.table ? "rgba(0,199,183,.08)" : "transparent",
                  borderLeft: activeTable === t.table ? "3px solid var(--teal-500)" : "3px solid transparent",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                <span style={{ fontWeight: activeTable === t.table ? 700 : 400 }}>
                  {t.table.replace("tiq_", "")}
                </span>
                <span className="tiq-badge tiq-badge-slate" style={{ fontSize: 10 }}>{t.rows}</span>
              </div>
            ))}
          </div>

          {/* TABLE CONTENT */}
          <div>
            {!activeTable ? (
              <div className="tiq-card">
                <div className="tiq-empty">
                  <Database size={40} />
                  <div className="tiq-empty-title">Select a table</div>
                  <div>Click any table on the left to browse its records</div>
                </div>
              </div>
            ) : (
              <>
                {/* INSERT NEW ROW */}
                {newRow && (
                  <div className="tiq-card tiq-mb-4" style={{ border: "2px solid var(--teal-500)" }}>
                    <div className="tiq-card-title">Insert New Row into {activeTable}</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 12 }}>
                      {editableSchema.map((c: any) => (
                        <div key={c.column_name} className="tiq-form-group">
                          <label className="tiq-label">{c.column_name} <span style={{color:"var(--text-muted)",fontWeight:400}}>({c.data_type})</span></label>
                          <input className="tiq-input" value={newData[c.column_name] || ""}
                            onChange={e => setNewData((p: any) => ({...p, [c.column_name]: e.target.value}))} />
                        </div>
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="tiq-btn tiq-btn-primary" onClick={() => insertMut.mutate(newData)}>
                        <Plus size={14} /> Insert Row
                      </button>
                      <button className="tiq-btn tiq-btn-outline" onClick={() => { setNewRow(false); setNewData({}); }}>Cancel</button>
                    </div>
                  </div>
                )}

                {/* EDIT ROW PANEL */}
                {editRow && (
                  <div className="tiq-card tiq-mb-4" style={{ border: "2px solid var(--amber-400)" }}>
                    <div className="tiq-card-title">Edit Row ID {editRow.id}</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 12 }}>
                      {Object.entries(editRow).filter(([k]) => k !== "id").map(([k, v]) => (
                        <div key={k} className="tiq-form-group">
                          <label className="tiq-label">{k}</label>
                          <input className="tiq-input" value={String(v ?? "")}
                            onChange={e => setEditRow((p: any) => ({...p, [k]: e.target.value}))} />
                        </div>
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="tiq-btn tiq-btn-primary" onClick={() => updateMut.mutate({ id: editRow.id, data: editRow })}>
                        <Save size={14} /> Save
                      </button>
                      <button className="tiq-btn tiq-btn-outline" onClick={() => setEditRow(null)}>Cancel</button>
                    </div>
                  </div>
                )}

                {/* TABLE HEADER */}
                <div className="tiq-card" style={{ padding: 0 }}>
                  <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>
                      {activeTable} <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 400 }}>({total} rows)</span>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {selectedRowIds.length > 0 && (
                        <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                          onClick={() => { if (confirm(`Delete ${selectedRowIds.length} selected row(s)?`)) bulkDeleteMut.mutate(selectedRowIds as number[]); }}>
                          <Trash2 size={12} /> Delete {selectedRowIds.length} selected
                        </button>
                      )}
                      <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" onClick={() => refetchRows()}>
                        <RefreshCw size={12} />
                      </button>
                      <button className="tiq-btn tiq-btn-primary tiq-btn-sm" onClick={() => { setNewRow(true); setEditRow(null); }}>
                        <Plus size={13} /> New Row
                      </button>
                    </div>
                  </div>

                  {rowsLoading ? (
                    <div className="tiq-spinner-wrap"><div className="tiq-spinner" /></div>
                  ) : (
                    <DataTable
                      columns={cols}
                      rows={rows}
                      getRowKey={(row) => row.id}
                      rowStyle={(row) => editRow?.id === row.id ? { background: "rgba(251,191,36,.05)" } : undefined}
                      selectable
                      selectedKeys={selectedRowIds}
                      onSelectionChange={setSelectedRowIds}
                      actionsLabel="Actions"
                      emptyMessage="No records"
                      renderActions={(row) => (
                        <div style={{ display: "flex", gap: 4 }}>
                          <button className="tiq-btn tiq-btn-outline tiq-btn-sm"
                            onClick={() => { setEditRow({...row}); setNewRow(false); }}>Edit</button>
                          <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                            onClick={() => { if (confirm(`Delete row ${row.id}?`)) deleteMut.mutate(row.id); }}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    />
                  )}

                  {/* PAGINATION */}
                  {totalPages > 1 && (
                    <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        Page {page} of {totalPages} ({total} rows)
                      </span>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}>
                          <ChevronLeft size={13} />
                        </button>
                        <button className="tiq-btn tiq-btn-outline tiq-btn-sm" onClick={() => setPage(p => Math.min(totalPages, p+1))} disabled={page === totalPages}>
                          <ChevronRight size={13} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "sql" && (
        <div className="tiq-card">
          <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Play size={16} /> SQL Query Runner (SELECT only)
          </div>
          <textarea
            value={sqlQuery}
            onChange={e => setSqlQuery(e.target.value)}
            style={{ width: "100%", minHeight: 120, padding: 12, fontFamily: "monospace", fontSize: 13,
              border: "1.5px solid var(--border)", borderRadius: 8, resize: "vertical", outline: "none" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 10, marginBottom: 16 }}>
            <button className="tiq-btn tiq-btn-primary" onClick={runSql}>
              <Play size={14} /> Run Query
            </button>
            <div style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
              Only SELECT statements. Use Table Browser for edits.
            </div>
          </div>

          {sqlError && <div className="tiq-alert tiq-alert-error" style={{ fontFamily: "monospace", fontSize: 12 }}>{sqlError}</div>}

          {sqlResult && (
            <div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                {sqlResult.count} row(s) returned
              </div>
              <DataTable
                columns={sqlResult.columns}
                rows={sqlResult.rows}
                getRowKey={(_row, i) => i}
                emptyMessage="No rows returned"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}