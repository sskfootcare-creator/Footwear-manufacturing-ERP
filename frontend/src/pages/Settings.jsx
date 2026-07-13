import { useEffect, useState } from "react";
import { http } from "../lib/api";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  ConfirmDialog,
} from "../components/ui-kit";
import {
  Clock,
  RotateCcw,
  Save,
  Check,
  Package,
  Upload,
  Trash2,
  FileSpreadsheet,
  Settings2,
  History,
} from "lucide-react";

const STAGE_LABEL = {
  procurement: "Procurement",
  cutting: "Cutting",
  folding: "Folding",
  attachment: "Attachment",
  stitching: "Stitching",
  lasting: "Lasting",
  sole_pasting: "Sole Pasting",
  finishing: "Finishing",
  qc_pack: "QC & Pack",
};

const STAGE_ORDER = [
  "procurement",
  "cutting",
  "folding",
  "attachment",
  "stitching",
  "lasting",
  "sole_pasting",
  "finishing",
  "qc_pack",
];

export default function Settings() {
  const [hours, setHours] = useState({});
  const [defaults, setDefaults] = useState({});
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await http.get("/settings/stage-durations");
    setHours(data.hours || {});
    setDefaults(data.defaults || {});
  };
  useEffect(() => {
    load();
  }, []);

  const setStage = (k, v) => setHours((h) => ({ ...h, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = { hours: {} };
      STAGE_ORDER.forEach((k) => {
        payload.hours[k] = Number(hours[k] || 0);
      });
      await http.put("/settings/stage-durations", payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const resetToDefault = () => setHours({ ...defaults });

  const totalHours = STAGE_ORDER.reduce((s, k) => s + Number(hours[k] || 0), 0);

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="System / ETA Configuration"
        testId="settings-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary
              onClick={resetToDefault}
              data-testid="reset-defaults-btn"
              className="px-3 sm:px-5"
            >
              <RotateCcw className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">Reset to default</span>
            </BtnSecondary>
            <BtnPrimary
              onClick={save}
              disabled={saving}
              data-testid="save-settings-btn"
              className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36] px-3 sm:px-5"
            >
              {saved ? (
                <>
                  <Check className="w-3.5 h-3.5 inline -mt-0.5" />
                  <span className="hidden sm:inline ml-1">Saved</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5 inline -mt-0.5" />
                  <span className="hidden sm:inline ml-1">{saving ? "Saving..." : "Save"}</span>
                </>
              )}
            </BtnPrimary>
          </div>
        }
      />
      <div className="p-4 sm:p-8 space-y-6 max-w-4xl mx-auto">
        <Card className="p-6">
          <div className="flex items-baseline justify-between mb-1">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#C27842]" /> Stage ETA / Deadline
              (hours)
            </h2>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
              Total ETA:{" "}
              <span className="font-mono text-slate-900">
                {totalHours} hrs ≈ {(totalHours / 24).toFixed(1)} days
              </span>
            </div>
          </div>
          <p className="text-xs text-slate-600 mb-5">
            Maximum allowed time for a job to remain in each production stage.
            Once a stage is exceeded, the job appears in the <b>Overdue</b>{" "}
            alert on the Dashboard and is highlighted on the Production floor.
          </p>

          <div className="space-y-2" data-testid="stage-duration-list">
            {STAGE_ORDER.map((k) => (
              <div
                key={k}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 border-2 border-slate-200 px-4 py-3 hover:border-[#C27842] transition-colors"
              >
                <div className="w-full sm:w-44 font-bold uppercase tracking-wider text-sm">
                  {STAGE_LABEL[k]}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={hours[k] ?? ""}
                    onChange={(e) => setStage(k, e.target.value)}
                    data-testid={`duration-input-${k}`}
                    className="w-24 sm:w-28 border-2 border-slate-300 px-3 py-1.5 sm:py-2 font-mono text-base sm:text-lg focus:border-[#C27842] focus:outline-none"
                  />
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">
                    hours
                  </span>
                  <span className="text-xs text-slate-500 ml-1">
                    ≈ {(Number(hours[k] || 0) / 24).toFixed(1)} days
                  </span>
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 sm:ml-auto">
                  Default:{" "}
                  <span className="font-mono font-bold">{defaults[k]}h</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5 bg-orange-50 border-orange-200">
          <div className="text-xs text-slate-700 leading-relaxed">
            <b className="text-[#C27842]">How this works:</b> Whenever a
            production job moves to a new stage, the system records the entry
            time and computes a deadline as <i>entry + stage hours</i>. If the
            deadline passes without the job moving forward, it appears in the{" "}
            <b>Overdue</b> widget on the Dashboard and the Production board card
            turns red with an alert badge. Existing jobs use these settings on
            their next stage transition.
          </div>
        </Card>

        <PackingTemplatesSection />
        <CompanyProfileSection />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <BackupExportSection />
          <ActivityFeedSection />
        </div>
      </div>
    </div>
  );
}

/* -------------------- PACKING TEMPLATES SECTION -------------------- */
function PackingTemplatesSection() {
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({
    client_name: "",
    name: "",
    aliases: "",
    file_b64: "",
    file_name: "",
  });
  const [uploading, setUploading] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    const { data } = await http.get("/packing-templates");
    setTemplates(data || []);
  };
  useEffect(() => {
    load();
  }, []);

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = String(reader.result).split(",", 2)[1] || "";
      setForm((s) => ({ ...s, file_b64: b64, file_name: f.name }));
    };
    reader.readAsDataURL(f);
  };

  const upload = async () => {
    if (!form.client_name || !form.name || !form.file_b64) {
      alert("Client name, template name and Excel file are required.");
      return;
    }
    setUploading(true);
    try {
      const aliases = form.aliases
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await http.post("/packing-templates", {
        client_name: form.client_name,
        name: form.name,
        aliases,
        file_b64: form.file_b64,
      });
      setForm({
        client_name: "",
        name: "",
        aliases: "",
        file_b64: "",
        file_name: "",
      });
      load();
    } catch (e) {
      alert("Upload failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setUploading(false);
    }
  };

  const remove = (t) => {
    setConfirm({
      title: "Delete Packing Template",
      message: `Are you sure you want to delete the packing-list template "${t.name}"?`,
      onConfirm: async () => {
        await http.delete(`/packing-templates/${t.id}`);
        setConfirm(null);
        load();
      },
    });
  };

  return (
    <Card className="p-6" data-testid="packing-templates-section">
      <h2 className="text-xl font-bold flex items-center gap-2 mb-1">
        <Package className="w-5 h-5 text-[#16A34A]" /> Packing-List Templates
      </h2>
      <p className="text-xs text-slate-600 mb-5">
        Upload custom Excel layouts your clients require. Use{" "}
        <code className="bg-slate-100 px-1">{`{{po_number}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{client_name}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{vendor_name}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{carton_dim}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{dispatch_date}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{transporter}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{vehicle_no}}`}</code>,{" "}
        <code className="bg-slate-100 px-1">{`{{notes}}`}</code> etc. as
        placeholders, and mark the line-item row with the cell{" "}
        <code className="bg-slate-100 px-1">{`{{lines}}`}</code>. The system
        auto-picks the template whose <b>alias</b> matches the PO client name.
      </p>

      <div className="bg-slate-50 border-2 border-dashed border-slate-300 p-4 mb-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <input
            value={form.client_name}
            onChange={(e) =>
              setForm((s) => ({ ...s, client_name: e.target.value }))
            }
            placeholder="Client name (eg. NEXTGEN FASTFASHION LIMITED)"
            data-testid="pt-client-name"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
          />
          <input
            value={form.name}
            onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))}
            placeholder="Template label (eg. SHEIN std)"
            data-testid="pt-name"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
          />
          <input
            value={form.aliases}
            onChange={(e) =>
              setForm((s) => ({ ...s, aliases: e.target.value }))
            }
            placeholder="Aliases (comma-separated: shein, nextgen, ril)"
            data-testid="pt-aliases"
            className="border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
          />
        </div>
        <div className="flex items-center gap-3">
          <label
            className="cursor-pointer inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wider border-2 border-slate-300 hover:border-[#0F172A] px-4 py-2"
            data-testid="pt-file-label"
          >
            <Upload className="w-4 h-4" /> {form.file_name || "Pick xlsx file"}
            <input
              type="file"
              accept=".xlsx"
              onChange={pickFile}
              className="hidden"
              data-testid="pt-file-input"
            />
          </label>
          <BtnPrimary
            onClick={upload}
            disabled={uploading}
            data-testid="pt-upload"
            className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]"
          >
            {uploading ? "Uploading…" : "Save template"}
          </BtnPrimary>
        </div>
      </div>

      {templates.length === 0 ? (
        <div
          className="text-center text-slate-400 text-sm py-8"
          data-testid="pt-empty"
        >
          No custom templates yet. The default SSK layout is used until you add
          one.
        </div>
      ) : (
        <table className="w-full text-sm" data-testid="pt-list">
          <thead className="bg-slate-50 border-b-2 border-slate-200">
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
              <th className="px-4 py-2 font-bold">Client</th>
              <th className="px-4 py-2 font-bold">Template</th>
              <th className="px-4 py-2 font-bold">Aliases</th>
              <th className="px-4 py-2 font-bold">Created</th>
              <th className="px-4 py-2 font-bold text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr
                key={t.id}
                className="border-b border-slate-100 hover:bg-slate-50"
                data-testid={`pt-row-${t.id}`}
              >
                <td className="px-4 py-2 font-bold">{t.client_name}</td>
                <td className="px-4 py-2 flex items-center gap-2">
                  <FileSpreadsheet className="w-3.5 h-3.5 text-[#16A34A]" />{" "}
                  {t.name}
                </td>
                <td className="px-4 py-2 text-xs text-slate-600 font-mono">
                  {(t.aliases || []).join(", ") || "—"}
                </td>
                <td className="px-4 py-2 text-xs text-slate-500 font-mono">
                  {(t.created_at || "").slice(0, 10)}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => remove(t)}
                    className="text-slate-600 hover:text-red-600 p-1.5"
                    data-testid={`pt-delete-${t.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />
    </Card>
  );
}

/* -------------------- COMPANY PROFILE SECTION -------------------- */
function CompanyProfileSection() {
  const [form, setForm] = useState({
    name: "",
    address1: "",
    address2: "",
    address3: "",
    gstin: "",
    state: "",
    state_code: "",
    bank_acc: "",
    bank_ifsc: "",
    bank_name: "",
    phone: "",
    email: "",
  });
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await http.get("/settings/company");
      setForm(data);
    } catch (e) {
      alert("Failed to load company profile: " + e.message);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await http.put("/settings/company", form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      alert(
        "Failed to save company profile: " +
          (e.response?.data?.detail || e.message),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-6" data-testid="company-profile-section">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Settings2 className="w-5 h-5 text-[#C27842]" /> Company Profile (PDF
          Branding)
        </h2>
        <BtnPrimary
          onClick={save}
          disabled={saving}
          data-testid="save-profile-btn"
          className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]"
        >
          {saved ? (
            <>
              <Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Saved
            </>
          ) : (
            <>
              <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />{" "}
              {saving ? "Saving..." : "Save Profile"}
            </>
          )}
        </BtnPrimary>
      </div>
      <p className="text-xs text-slate-600 mb-5">
        Configure the official legal entity name, address lines, GSTIN, and bank
        account information. These details are dynamically rendered on invoices,
        packing lists, and dispatch challans.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <Input
            label="Company Name"
            value={form.name}
            onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))}
            testId="profile-name"
          />
        </div>
        <Input
          label="Address Line 1"
          value={form.address1}
          onChange={(e) => setForm((s) => ({ ...s, address1: e.target.value }))}
        />
        <Input
          label="Address Line 2"
          value={form.address2}
          onChange={(e) => setForm((s) => ({ ...s, address2: e.target.value }))}
        />
        <Input
          label="Address Line 3 / City / PIN"
          value={form.address3}
          onChange={(e) => setForm((s) => ({ ...s, address3: e.target.value }))}
        />
        <Input
          label="GSTIN"
          value={form.gstin}
          onChange={(e) => setForm((s) => ({ ...s, gstin: e.target.value }))}
          testId="profile-gstin"
        />
        <Input
          label="State"
          value={form.state}
          onChange={(e) => setForm((s) => ({ ...s, state: e.target.value }))}
        />
        <Input
          label="State Code"
          value={form.state_code}
          onChange={(e) =>
            setForm((s) => ({ ...s, state_code: e.target.value }))
          }
        />
        <Input
          label="Bank Name"
          value={form.bank_name}
          onChange={(e) =>
            setForm((s) => ({ ...s, bank_name: e.target.value }))
          }
        />
        <Input
          label="Bank Account Number"
          value={form.bank_acc}
          onChange={(e) => setForm((s) => ({ ...s, bank_acc: e.target.value }))}
        />
        <Input
          label="Bank Branch IFSC"
          value={form.bank_ifsc}
          onChange={(e) =>
            setForm((s) => ({ ...s, bank_ifsc: e.target.value }))
          }
        />
        <Input
          label="Phone"
          value={form.phone}
          onChange={(e) => setForm((s) => ({ ...s, phone: e.target.value }))}
        />
        <Input
          label="Email"
          value={form.email}
          onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))}
        />
      </div>
    </Card>
  );
}

/* -------------------- DATABASE BACKUP & EXPORT SECTION -------------------- */
function BackupExportSection() {
  const [downloading, setDownloading] = useState(false);

  const downloadBackup = async () => {
    setDownloading(true);
    try {
      const { data } = await http.get("/settings/export-backup");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ssk_erp_backup_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Failed to export backup: " + e.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Card
      className="p-6 h-full flex flex-col justify-between"
      data-testid="backup-export-section"
    >
      <div>
        <h2 className="text-xl font-bold flex items-center gap-2 mb-1">
          <FileSpreadsheet className="w-5 h-5 text-[#2563EB]" /> Database Backup
          & Export
        </h2>
        <p className="text-xs text-slate-600 mb-5">
          Download a complete snapshot of all collections (materials, styles,
          POs, workers, settings, and logs) in a structured JSON format. This
          backup can be stored securely for data retention and business
          continuity.
        </p>
      </div>
      <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
        <span className="text-[10px] text-slate-500 font-mono">
          Format: JSON File
        </span>
        <BtnPrimary
          onClick={downloadBackup}
          disabled={downloading}
          data-testid="download-backup-btn"
        >
          {downloading ? "Exporting..." : "Download Full Backup"}
        </BtnPrimary>
      </div>
    </Card>
  );
}

/* -------------------- SYSTEM ACTIVITY FEED SECTION -------------------- */
function ActivityFeedSection() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await http.get("/settings/audit-logs");
      setLogs(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <Card className="p-6 h-full" data-testid="activity-feed-section">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <History className="w-5 h-5 text-[#C27842]" /> System Activity Feed
        </h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs font-bold uppercase tracking-wider text-[#C27842] hover:text-[#A65D24]"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      <div className="max-h-[350px] overflow-y-auto pr-1 space-y-4">
        {logs.length === 0 ? (
          <div className="text-center text-slate-400 text-xs py-8">
            No recent activity logs.
          </div>
        ) : (
          <div className="relative border-l border-slate-200 pl-4 ml-2 space-y-4">
            {logs.map((log) => (
              <div key={log.id} className="relative">
                <div className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-[#C27842] border-2 border-white" />
                <div className="text-xs">
                  <span className="font-bold text-slate-900">
                    {log.details}
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5 font-mono">
                  {log.by} · {new Date(log.created_at).toLocaleString("en-IN")}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
