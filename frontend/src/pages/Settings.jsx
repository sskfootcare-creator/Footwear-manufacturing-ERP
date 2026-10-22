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
  Mail,
  Send,
  Eye,
  EyeOff,
  ExternalLink,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  ShieldCheck,
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
        <GmailSettingsSection />

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
        <div className="overflow-x-auto">
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
        </div>
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

/* -------------------- GMAIL & EMAIL SETTINGS SECTION -------------------- */
function GmailSettingsSection() {
  const [config, setConfig] = useState({
    gmail_user: "",
    gmail_app_password: "",
    from_name: "SSK Footcare Manufacturing",
    reply_to: "",
    default_cc: "",
    smtp_host: "smtp.gmail.com",
    smtp_port: 465,
    is_configured: false,
    has_app_password: false,
    masked_app_password: "",
    source: "none",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [statusMsg, setStatusMsg] = useState(null);
  const [testModal, setTestModal] = useState(false);
  const [testRecipient, setTestRecipient] = useState("");

  const load = async () => {
    try {
      setLoading(true);
      const { data } = await http.get("/settings/email");
      setConfig((prev) => ({
        ...prev,
        ...data,
        gmail_app_password: "",
      }));
    } catch (err) {
      console.error("Failed to load email settings", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSave = async (verifyFirst = false) => {
    if (!config.gmail_user) {
      setStatusMsg({ type: "error", text: "Please enter your company Gmail address." });
      return;
    }
    if (!config.has_app_password && !config.gmail_app_password) {
      setStatusMsg({
        type: "error",
        text: "Please enter the 16-character Google App Password (generated in Google Account Security).",
      });
      return;
    }
    setSaving(true);
    setStatusMsg(null);
    try {
      const payload = {
        gmail_user: config.gmail_user.trim(),
        gmail_app_password: config.gmail_app_password,
        from_name: config.from_name,
        reply_to: config.reply_to,
        default_cc: config.default_cc,
        smtp_host: config.smtp_host || "smtp.gmail.com",
        smtp_port: Number(config.smtp_port) || 465,
        verify_now: verifyFirst,
      };
      await http.put("/settings/email", payload);
      setStatusMsg({
        type: "success",
        text: verifyFirst
          ? "Gmail connection verified and settings saved successfully!"
          : "Gmail settings saved successfully!",
      });
      load();
    } catch (e) {
      setStatusMsg({
        type: "error",
        text: e.response?.data?.detail || e.message || "Failed to save settings",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleVerifyOnly = async () => {
    if (!config.gmail_user) {
      setStatusMsg({ type: "error", text: "Please enter your company Gmail address." });
      return;
    }
    if (!config.has_app_password && !config.gmail_app_password) {
      setStatusMsg({ type: "error", text: "Please enter the Google App Password to test." });
      return;
    }
    setVerifying(true);
    setStatusMsg(null);
    try {
      const { data } = await http.post("/settings/email/verify", {
        gmail_user: config.gmail_user.trim(),
        gmail_app_password: config.gmail_app_password,
      });
      if (data.ok) {
        setStatusMsg({ type: "success", text: "Verification Succeeded! " + data.message });
      } else {
        setStatusMsg({ type: "error", text: data.message });
      }
    } catch (e) {
      setStatusMsg({
        type: "error",
        text: e.response?.data?.detail || e.message || "Verification failed",
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleSendTestEmail = async () => {
    if (!testRecipient) {
      alert("Please provide a recipient email address.");
      return;
    }
    setTesting(true);
    try {
      const { data } = await http.post("/settings/email/test", {
        test_recipient: testRecipient.trim(),
      });
      alert(data.message || "Test email sent successfully!");
      setTestModal(false);
      setTestRecipient("");
    } catch (e) {
      alert("Test email failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card className="p-6" data-testid="gmail-settings-section">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Mail className="w-5 h-5 text-[#C27842]" /> Company Gmail & Email Integration
            </h2>
            {config.is_configured ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold bg-green-100 text-green-800 border border-green-300">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                Gmail Connected
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                Not Configured
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Connect your company Google/Gmail account to directly email Invoice Payment Reminders, statements, and dispatch advisories to clients.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowHelp(!showHelp)}
            className="text-xs text-slate-600 hover:text-slate-900 border border-slate-300 px-2.5 py-1.5 rounded flex items-center gap-1 hover:bg-slate-50 transition-colors"
          >
            <HelpCircle className="w-3.5 h-3.5 text-[#C27842]" />
            <span>{showHelp ? "Hide Guide" : "App Password Guide"}</span>
          </button>
          {config.is_configured && (
            <BtnSecondary
              onClick={() => setTestModal(true)}
              className="text-xs px-3 py-1.5"
              data-testid="send-test-email-btn"
            >
              <Send className="w-3.5 h-3.5 inline mr-1" />
              Send Test Email
            </BtnSecondary>
          )}
        </div>
      </div>

      {/* Help box */}
      {showHelp && (
        <div className="mb-5 p-4 bg-slate-50 border-2 border-slate-200 rounded text-xs space-y-2 text-slate-700">
          <div className="font-bold text-slate-900 flex items-center gap-1.5 text-sm">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            How to generate a 16-character Google App Password (Required for Gmail SMTP):
          </div>
          <ol className="list-decimal list-inside space-y-1 text-slate-600 pl-1">
            <li>Log into your company Google / Gmail account at <a href="https://myaccount.google.com" target="_blank" rel="noreferrer" className="text-blue-600 underline font-semibold">myaccount.google.com <ExternalLink className="w-3 h-3 inline" /></a>.</li>
            <li>Go to <b>Security</b> and ensure <b>2-Step Verification</b> is turned ON.</li>
            <li>In the search bar at top of Google Account, search for <b>App Passwords</b> (or visit <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="text-blue-600 underline font-semibold">myaccount.google.com/apppasswords <ExternalLink className="w-3 h-3 inline" /></a>).</li>
            <li>Enter an App name (e.g. <code>SSK Footcare ERP</code>) and click <b>Create</b>.</li>
            <li>Google will show a 16-letter password (e.g. <code>abcd efgh ijkl mnop</code>). Paste it into the <b>Google App Password</b> field below and click <b>Save & Verify</b>.</li>
          </ol>
          <div className="text-[11px] text-slate-500 pt-1">
            Note: You do NOT need to give your regular Gmail login password. The 16-character App Password is safer and specifically designed for business ERP applications.
          </div>
        </div>
      )}

      {/* Status Alert Banner */}
      {statusMsg && (
        <div
          className={`mb-4 p-3 rounded text-xs flex items-center justify-between border ${
            statusMsg.type === "success"
              ? "bg-green-50 text-green-800 border-green-200"
              : "bg-red-50 text-red-800 border-red-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {statusMsg.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-green-600" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-600" />
            )}
            <span>{statusMsg.text}</span>
          </div>
          <button onClick={() => setStatusMsg(null)} className="text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          label="Company Gmail Address"
          placeholder="e.g. billing@sskfootcare.com or company@gmail.com"
          value={config.gmail_user}
          onChange={(e) => setConfig((s) => ({ ...s, gmail_user: e.target.value }))}
          testId="email-user-input"
        />

        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1 flex items-center justify-between">
            <span>Google App Password (16 characters)</span>
            {config.has_app_password && !config.gmail_app_password && (
              <span className="text-[10px] text-green-600 font-semibold lowercase">
                configured ({config.masked_app_password})
              </span>
            )}
          </div>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              placeholder={
                config.has_app_password
                  ? "Password configured (leave blank to keep)"
                  : "e.g. abcd efgh ijkl mnop"
              }
              value={config.gmail_app_password}
              onChange={(e) => setConfig((s) => ({ ...s, gmail_app_password: e.target.value }))}
              data-testid="email-password-input"
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none font-mono pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
              title={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <Input
          label="Sender Display Name"
          placeholder="e.g. SSK Footcare Manufacturing"
          value={config.from_name}
          onChange={(e) => setConfig((s) => ({ ...s, from_name: e.target.value }))}
          testId="email-from-name"
        />

        <Input
          label="Default CC Email (optional)"
          placeholder="e.g. accounts@sskfootcare.com"
          value={config.default_cc}
          onChange={(e) => setConfig((s) => ({ ...s, default_cc: e.target.value }))}
          testId="email-default-cc"
        />

        <Input
          label="Reply-To Email (optional)"
          placeholder="e.g. finance@sskfootcare.com"
          value={config.reply_to}
          onChange={(e) => setConfig((s) => ({ ...s, reply_to: e.target.value }))}
          testId="email-reply-to"
        />

        <div className="grid grid-cols-2 gap-2">
          <Input
            label="SMTP Host"
            value={config.smtp_host}
            onChange={(e) => setConfig((s) => ({ ...s, smtp_host: e.target.value }))}
          />
          <Input
            label="SMTP Port"
            value={config.smtp_port}
            onChange={(e) => setConfig((s) => ({ ...s, smtp_port: e.target.value }))}
          />
        </div>
      </div>

      <div className="mt-5 pt-4 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] text-slate-500">
          {config.updated_at ? (
            <span>Last updated: {new Date(config.updated_at).toLocaleString()}</span>
          ) : config.source === "environment" ? (
            <span>Loaded from environment variables (.env)</span>
          ) : (
            <span>Enter credentials and click Save & Verify Connection</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <BtnSecondary
            onClick={handleVerifyOnly}
            disabled={verifying || saving || !config.gmail_user}
            data-testid="verify-email-btn"
            className="px-3 py-2 text-xs"
          >
            {verifying ? "Testing..." : "Test Connection"}
          </BtnSecondary>
          <BtnPrimary
            onClick={() => handleSave(true)}
            disabled={saving || verifying || !config.gmail_user}
            data-testid="save-email-btn"
            className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36] px-4 py-2 text-xs"
          >
            {saving ? "Saving & Verifying..." : "Save & Verify Connection"}
          </BtnPrimary>
        </div>
      </div>

      {/* Test Email Modal */}
      {testModal && (
        <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4">
          <div className="bg-white w-full max-w-md border-2 border-slate-200 shadow-xl p-5">
            <h3 className="text-base font-bold text-slate-900 mb-1 flex items-center gap-2">
              <Mail className="w-4 h-4 text-[#C27842]" /> Send Test Email
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              Send a test advisory message from <b>{config.gmail_user}</b> to verify real email delivery.
            </p>
            <div className="space-y-3">
              <Input
                label="Recipient Email Address"
                placeholder="your.email@company.com"
                value={testRecipient}
                onChange={(e) => setTestRecipient(e.target.value)}
                autoFocus
              />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <BtnSecondary onClick={() => setTestModal(false)} disabled={testing}>
                Cancel
              </BtnSecondary>
              <BtnPrimary
                onClick={handleSendTestEmail}
                disabled={testing || !testRecipient}
                className="bg-[#0F172A]"
              >
                {testing ? "Sending..." : "Send Test"}
              </BtnPrimary>
            </div>
          </div>
        </div>
      )}
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
