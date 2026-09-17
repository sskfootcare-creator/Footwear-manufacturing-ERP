import { useEffect, useState } from "react";
import { http, formatApiError } from "../lib/api";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
  ConfirmDialog,
} from "../components/ui-kit";
import { useNavigate } from "react-router-dom";
import { Drawer } from "./Materials";
import { Plus, Trash2, Pencil, Save, UserX, UserCheck, KeyRound, HardHat, ShieldCheck, CheckSquare, Square } from "lucide-react";

const ROLES = [
  "admin", "manager", "ca", "accountant",
  "production_manager", "production",
  "inventory_manager", "sales_manager", "sales",
  "online_manager", "custom",
];
const empty = { email: "", name: "", role: "production", role_title: "", allowed_modules: null, password: "" };

export default function Users() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [modulesData, setModulesData] = useState({ modules: {}, role_defaults: {} });
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(empty);
  const [confirm, setConfirm] = useState(null);
  const [error, setError] = useState("");

  // Password-reset drawer state (admin sets any user's password directly)
  const [resetTarget, setResetTarget] = useState(null); // {id, email, name}
  const [resetPwd, setResetPwd] = useState("");
  const [resetConfirm, setResetConfirm] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetDone, setResetDone] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);

  const openReset = (u) => {
    setResetTarget(u);
    setResetPwd("");
    setResetConfirm("");
    setResetError("");
    setResetDone(false);
  };
  const submitReset = async (e) => {
    e.preventDefault();
    setResetError("");
    if (resetPwd.length < 8) return setResetError("Password must be at least 8 characters long.");
    if (resetPwd !== resetConfirm) return setResetError("Passwords do not match.");
    setResetBusy(true);
    try {
      await http.patch(`/users/${resetTarget.id}`, { password: resetPwd });
      setResetDone(true);
    } catch (e2) {
      setResetError(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally {
      setResetBusy(false);
    }
  };

  const load = async () => {
    const { data } = await http.get("/users");
    setUsers(data);
  };
  const loadModules = async () => {
    try {
      const { data } = await http.get("/auth/modules");
      if (data && data.modules) setModulesData(data);
    } catch {}
  };
  useEffect(() => {
    load();
    loadModules();
  }, []);

  const handleRoleChange = (newRole) => {
    const defs = modulesData.role_defaults?.[newRole] || [];
    setForm({
      ...form,
      role: newRole,
      allowed_modules: newRole === "admin" ? null : [...defs],
    });
  };

  const toggleModule = (modKey) => {
    const current = form.allowed_modules !== null
      ? form.allowed_modules
      : (modulesData.role_defaults?.[form.role] || []);
    let updated;
    if (current.includes(modKey)) {
      updated = current.filter((k) => k !== modKey);
    } else {
      updated = [...current, modKey];
    }
    setForm({ ...form, allowed_modules: updated });
  };

  const startNew = () => {
    setEditId(null);
    setForm({ ...empty, active: true, allowed_modules: [...(modulesData.role_defaults?.["production"] || [])] });
    setError("");
    setOpen(true);
  };
  const startEdit = (u) => {
    setEditId(u.id);
    const existingMods = u.allowed_modules !== undefined && u.allowed_modules !== null
      ? u.allowed_modules
      : (u.role === "admin" ? null : (modulesData.role_defaults?.[u.role] || []));
    setForm({
      email: u.email,
      name: u.name,
      role: u.role,
      role_title: u.role_title || "",
      allowed_modules: existingMods,
      active: u.active !== false,
      password: "",
    });
    setError("");
    setOpen(true);
  };
  const save = async () => {
    setError("");
    if (!editId && (!form.password || form.password.length < 8)) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (editId && form.password && form.password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    try {
      const payloadMods = form.role === "admin" ? null : form.allowed_modules;
      if (editId) {
        const body = {
          name: form.name,
          role: form.role,
          role_title: form.role_title,
          allowed_modules: payloadMods,
          active: form.active,
        };
        if (form.password) body.password = form.password;
        await http.patch(`/users/${editId}`, body);
      } else {
        const body = {
          ...form,
          allowed_modules: payloadMods,
        };
        await http.post("/users", body);
      }
      setOpen(false);
      load();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message);
    }
  };
  const remove = (id) => {
    setConfirm({
      title: "Deactivate User",
      message:
        "Are you sure you want to deactivate this user? Deactivated users cannot log in, but their historical records are preserved.",
      onConfirm: async () => {
        await http.delete(`/users/${id}`);
        setConfirm(null);
        load();
      },
    });
  };

  const toggleActive = async (u) => {
    try {
      await http.patch(`/users/${u.id}`, { active: true });
      load();
    } catch (e) {
      alert(formatApiError(e.response?.data?.detail) || e.message);
    }
  };

  const roleColor = {
    admin: "red",
    manager: "orange",
    ca: "purple",
    accountant: "purple",
    production_manager: "blue",
    production: "blue",
    inventory_manager: "amber",
    sales_manager: "emerald",
    sales: "emerald",
    online_manager: "indigo",
    custom: "slate",
  };

  return (
    <div>
      <PageHeader
        title="Users & Roles"
        subtitle="Admin / Users"
        testId="users-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={() => navigate("/workers")} data-testid="manage-karigars-btn">
              <HardHat className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Karigars / PINs
            </BtnSecondary>
            <BtnPrimary onClick={startNew} data-testid="add-user-btn">
              <Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Add User
            </BtnPrimary>
          </div>
        }
      />
      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        {/* Banner explaining Karigar (Worker) accounts */}
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 sm:p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs sm:text-sm text-slate-700">
          <div className="flex items-start gap-3">
            <div className="p-2 bg-amber-500/20 rounded-md text-amber-700 flex-shrink-0">
              <HardHat className="w-4 h-4" />
            </div>
            <div>
              <span className="font-bold text-slate-900">Looking for Karigar (Worker) logins?</span>{" "}
              Karigars do not use email passwords. They authenticate via <span className="font-bold text-amber-700">Phone + PIN</span> on the dedicated mobile app. Manage Karigar profiles and set PINs in <span className="font-semibold">Master → Karigars / Labour</span>.
            </div>
          </div>
          <BtnSecondary
            onClick={() => navigate("/workers")}
            className="text-xs shrink-0 self-end sm:self-center"
          >
            Go to Karigars →
          </BtnSecondary>
        </div>

        <Card className="overflow-hidden">

          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="users-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-3 font-bold">Name</th>
                  <th className="px-4 py-3 font-bold">Email</th>
                  <th className="px-4 py-3 font-bold">Role</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className={`border-b border-slate-100 hover:bg-slate-50 transition-colors duration-150 ${
                      u.active === false ? "bg-slate-50/40 text-slate-400" : ""
                    }`}
                  >
                    <td
                      className={`px-4 py-3 font-bold ${u.active === false ? "line-through text-slate-400" : ""}`}
                    >
                      {u.name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-1.5">
                          <Badge color={roleColor[u.role] || "slate"}>{u.role}</Badge>
                          {u.role_title && (
                            <span className="text-[11px] font-medium text-slate-500 italic">
                              ({u.role_title})
                            </span>
                          )}
                        </div>
                        {u.role !== "admin" && Array.isArray(u.modules) && (
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {u.modules.slice(0, 3).map((m) => (
                              <span key={m} className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-mono rounded">
                                {m}
                              </span>
                            ))}
                            {u.modules.length > 3 && (
                              <span className="px-1.5 py-0.5 bg-slate-100 text-slate-500 text-[9px] font-mono rounded">
                                +{u.modules.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={u.active === false ? "red" : "green"}>
                        {u.active === false ? "Inactive" : "Active"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => startEdit(u)}
                        title="Edit User"
                        className="text-slate-600 hover:text-[#2563EB] hover:bg-blue-50 p-1.5 rounded transition-colors duration-150"
                        data-testid={`edit-user-${u.email}`}
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openReset(u)}
                        title="Reset Password"
                        className="text-slate-600 hover:text-amber-600 hover:bg-amber-50 p-1.5 rounded transition-colors duration-150 ml-1 inline-flex items-center justify-center"
                        data-testid={`reset-password-${u.email}`}
                      >
                        <KeyRound className="w-4 h-4" />
                      </button>
                      {u.active === false ? (
                        <button
                          onClick={() => toggleActive(u)}
                          title="Reactivate User"
                          className="text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 p-1.5 rounded transition-colors duration-150 ml-1 inline-flex items-center justify-center"
                        >
                          <UserCheck className="w-4 h-4" />
                        </button>
                      ) : (
                        <button
                          onClick={() => remove(u.id)}
                          title="Deactivate User"
                          className="text-slate-500 hover:text-red-600 hover:bg-red-50 p-1.5 rounded transition-colors duration-150 ml-1 inline-flex items-center justify-center"
                        >
                          <UserX className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {open && (
        <Drawer
          onClose={() => setOpen(false)}
          title={editId ? "Edit User" : "New User"}
        >
          <div className="space-y-3">
            <Input
              label="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              testId="form-user-name"
            />
            <Input
              label="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              disabled={!!editId}
              testId="form-user-email"
            />
            <Input
              label="Role Title / Designation (optional)"
              placeholder="e.g. Chief Accountant, Store Supervisor"
              value={form.role_title}
              onChange={(e) => setForm({ ...form, role_title: e.target.value })}
              testId="form-user-role-title"
            />
            <Select
              label="Role"
              value={form.role}
              onChange={(e) => handleRoleChange(e.target.value)}
              testId="form-user-role"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r.replace("_", " ").toUpperCase()}
                </option>
              ))}
            </Select>

            {/* Modular Permissions Matrix */}
            <div className="border border-slate-200 rounded-lg p-3 bg-slate-50/50 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-600" /> Modular Permissions Matrix
                </div>
                {form.role !== "admin" && (
                  <button
                    type="button"
                    onClick={() => {
                      const defs = modulesData.role_defaults?.[form.role] || [];
                      setForm({ ...form, allowed_modules: [...defs] });
                    }}
                    className="text-[10px] text-blue-600 hover:text-blue-800 font-semibold underline"
                  >
                    Reset to Role Defaults
                  </button>
                )}
              </div>

              {form.role === "admin" ? (
                <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 p-2.5 rounded font-medium">
                  Administrator role has unrestricted access to all modules and system settings.
                </div>
              ) : (
                <div className="space-y-1.5 pt-1">
                  {Object.entries(modulesData.modules || {}).map(([key, mod]) => {
                    const activeMods = form.allowed_modules !== null
                      ? form.allowed_modules
                      : (modulesData.role_defaults?.[form.role] || []);
                    const isChecked = activeMods.includes(key);
                    return (
                      <div
                        key={key}
                        onClick={() => toggleModule(key)}
                        className={`flex items-start gap-2.5 p-2 rounded cursor-pointer border text-left transition-colors duration-150 ${
                          isChecked
                            ? "bg-blue-50/80 border-blue-200 text-slate-900"
                            : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"
                        }`}
                      >
                        <div className="mt-0.5">
                          {isChecked ? (
                            <CheckSquare className="w-4 h-4 text-blue-600 shrink-0" />
                          ) : (
                            <Square className="w-4 h-4 text-slate-300 shrink-0" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold">{mod.name}</span>
                            <span className="text-[9px] px-1 bg-slate-200 text-slate-600 rounded uppercase font-mono">
                              {mod.category}
                            </span>
                          </div>
                          <div className="text-[10px] text-slate-500 truncate">{mod.description}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <Input
              label={editId ? "New password (optional)" : "Password"}
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              testId="form-user-password"
              minLength={8}
            />
            {error && (
              <div
                className="text-xs text-red-600 font-bold bg-red-50 border border-red-200 px-3 py-2"
                data-testid="user-form-error"
              >
                {error}
              </div>
            )}
            {editId && (
              <div className="flex items-center justify-between p-3 bg-slate-50 border-2 border-slate-200 hover:bg-slate-100/50 transition-all duration-200">
                <div>
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Account Status
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    Deactivated users cannot access the system.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setForm({ ...form, active: !form.active })}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                    form.active ? "bg-emerald-500" : "bg-slate-300"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                      form.active ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            )}
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-user-btn">
                <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
              </BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />

      {resetTarget && (
        <Drawer
          onClose={() => setResetTarget(null)}
          title={`Reset password — ${resetTarget.name}`}
        >
          <div className="space-y-3" data-testid="reset-password-drawer">
            <div className="p-3 bg-amber-50 border-2 border-amber-300 text-amber-900 text-xs">
              <div className="font-bold uppercase tracking-wider mb-1">Admin password reset</div>
              You&apos;re setting a new password directly for{" "}
              <span className="font-mono font-bold">{resetTarget.email}</span>. Share the new
              password with them through a secure channel — they can change it themselves after signing in.
            </div>
            {resetDone ? (
              <div className="p-3 border-2 border-emerald-500 bg-emerald-50 text-emerald-900" data-testid="reset-done">
                <div className="font-bold">Password updated for {resetTarget.email}.</div>
                <div className="text-xs mt-1">All active sessions may still work until their token expires. Ask the user to sign in with the new password.</div>
                <BtnSecondary className="mt-3" onClick={() => setResetTarget(null)}>Close</BtnSecondary>
              </div>
            ) : (
              <form onSubmit={submitReset} className="space-y-3">
                <Input
                  label="New Password"
                  type="password"
                  value={resetPwd}
                  onChange={(e) => setResetPwd(e.target.value)}
                  testId="reset-new-password"
                />
                <Input
                  label="Confirm Password"
                  type="password"
                  value={resetConfirm}
                  onChange={(e) => setResetConfirm(e.target.value)}
                  testId="reset-confirm-password"
                />
                {resetError && (
                  <div className="text-xs text-red-700 bg-red-50 border-2 border-red-300 px-3 py-2" data-testid="reset-error">
                    {resetError}
                  </div>
                )}
                <div className="flex gap-2 pt-1">
                  <BtnPrimary onClick={submitReset} disabled={resetBusy} data-testid="reset-submit-btn">
                    {resetBusy ? "Saving…" : "Set new password"}
                  </BtnPrimary>
                  <BtnSecondary onClick={() => setResetTarget(null)}>Cancel</BtnSecondary>
                </div>
              </form>
            )}
          </div>
        </Drawer>
      )}
    </div>
  );
}
