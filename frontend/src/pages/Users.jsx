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
import { Drawer } from "./Materials";
import { Plus, Trash2, Pencil, Save, UserX, UserCheck, KeyRound } from "lucide-react";

const ROLES = ["admin", "manager", "production", "sales"];
const empty = { email: "", name: "", role: "production", password: "" };

export default function Users() {
  const [users, setUsers] = useState([]);
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
  useEffect(() => {
    load();
  }, []);

  const startNew = () => {
    setEditId(null);
    setForm({ ...empty, active: true });
    setError("");
    setOpen(true);
  };
  const startEdit = (u) => {
    setEditId(u.id);
    setForm({
      email: u.email,
      name: u.name,
      role: u.role,
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
      if (editId) {
        const body = { name: form.name, role: form.role, active: form.active };
        if (form.password) body.password = form.password;
        await http.patch(`/users/${editId}`, body);
      } else {
        await http.post("/users", form);
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
    production: "blue",
    sales: "green",
  };

  return (
    <div>
      <PageHeader
        title="Users & Roles"
        subtitle="Admin / Users"
        testId="users-header"
        action={
          <BtnPrimary onClick={startNew} data-testid="add-user-btn">
            <Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Add User
          </BtnPrimary>
        }
      />
      <div className="p-2 sm:p-4 lg:p-8">
        <Card className="overflow-hidden">
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
                    <Badge color={roleColor[u.role]}>{u.role}</Badge>
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
            <Select
              label="Role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              testId="form-user-role"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
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
