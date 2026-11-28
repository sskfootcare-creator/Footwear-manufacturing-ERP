import { useState, useEffect, useCallback, useRef } from "react";
import { http, inr, getBackendUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  CheckCircle2,
  Circle,
  Plus,
  Inbox,
  Calendar,
  ShieldCheck,
  AlertTriangle,
  History,
  ShoppingCart,
  ListTodo,
  Send,
  Lock,
  RotateCcw,
  Camera,
  Mic,
  Square,
  Landmark,
  Banknote,
  ArrowRightLeft,
  Trash2,
  X,
  Clock,
  ChevronDown,
  ChevronRight,
  Loader2,
  Check,
  MessageSquare,
  ArrowLeft,
} from "lucide-react";

const PRIORITY_STYLES = {
  P0: { ring: "border-rose-500 text-rose-600", badge: "bg-rose-50 text-rose-700 border-rose-200", label: "P0 Urgent" },
  P1: { ring: "border-[#C27842] text-[#C27842]", badge: "bg-amber-50 text-[#C27842] border-amber-200", label: "P1 High" },
  P2: { ring: "border-sky-500 text-sky-600", badge: "bg-sky-50 text-sky-700 border-sky-200", label: "P2 Normal" },
};

const resolveMediaUrl = (url) => {
  if (!url) return "";
  return url.startsWith("/") ? `${getBackendUrl()}${url}` : url;
};

const NON_COMPLETION_REASONS = [
  "Material / Stock Shortage",
  "Machine Breakdown",
  "Waiting on Partner / Approval",
  "Vendor / Transport Delay",
  "Worker Absenteeism",
  "Shifted Priority",
  "Other",
];

export default function DailyTasks() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [lists, setLists] = useState([]);
  const [summary, setSummary] = useState({
    total_today: 0,
    done_today: 0,
    completion_pct: 0,
    pending_approval_count: 0,
    needs_input_count: 0,
    carried_forward_count: 0,
  });
  const [users, setUsers] = useState([]);
  const [expenseCategories, setExpenseCategories] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);

  // Navigation state: "today" | "all" | "approvals" | "needs_input" | "history" | "list:<id>"
  const [activeNav, setActiveNav] = useState("today");
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [comments, setComments] = useState([]);
  const [loadingComments, setLoadingComments] = useState(false);
  const [showCompletedDrawer, setShowCompletedDrawer] = useState(false);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [banner, setBanner] = useState(null);

  // Quick Task Create
  const [quickTitle, setQuickTitle] = useState("");
  const [quickDueTime, setQuickDueTime] = useState("17:30");
  const [quickPriority, setQuickPriority] = useState("P1");
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskForm, setTaskForm] = useState({
    title: "",
    description: "",
    task_type: "staff_task",
    priority: "P1",
    due_time: "17:30",
    assignee_id: "",
    approver_id: "",
    erp_ref_type: "",
    erp_ref_label: "",
    photos: [],
    voice_notes: [],
  });
  const [recordingTarget, setRecordingTarget] = useState(null); // "task" | "comment" | null

  // Non-completion modal
  const [carryTask, setCarryTask] = useState(null);
  const [carryReason, setCarryReason] = useState({ category: NON_COMPLETION_REASONS[0], note: "" });

  // Comment composer + media
  const [msgText, setMsgText] = useState("");
  const [pendingPhotos, setPendingPhotos] = useState([]);
  const [pendingVoices, setPendingVoices] = useState([]);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordStartRef = useRef(0);
  const detailPaneRef = useRef(null);
  const threadEndRef = useRef(null);
  const audioFileInputRef = useRef(null);
  const audioFileTargetRef = useRef("comment");

  // Shopping List Modals & Quick Add
  const [showListModal, setShowListModal] = useState(false);
  const [newListForm, setNewListForm] = useState({ title: "", list_type: "shopping" });
  const [newItemForm, setNewItemForm] = useState({
    text: "",
    qty: "",
    expense_category: "Raw Materials",
    actual_amount: "",
    shop_note: "",
  });
  const [showSettleModal, setShowSettleModal] = useState(false);
  const [settleForm, setSettleForm] = useState({
    settlement_mode: "bank_transfer",
    bank_account_id: "",
    payee: "",
    notes: "",
  });
  const [settling, setSettling] = useState(false);

  const showToast = (text, type = "success") => {
    setBanner({ text, type });
    setTimeout(() => setBanner(null), 4000);
  };

  const fetchAll = useCallback(async () => {
    try {
      const viewParam = activeNav.startsWith("list:") ? "all" : activeNav;
      const [tasksRes, listsRes] = await Promise.all([
        http.get("/daily-tasks", { params: { view: viewParam } }),
        http.get("/daily-lists"),
      ]);
      const data = tasksRes.data || {};
      setTasks(data.tasks || []);
      setSummary(data.summary || {});
      setUsers(data.users || []);
      const cats = data.expense_categories || [];
      setExpenseCategories(cats);
      if (cats.length && !cats.includes(newItemForm.expense_category)) {
        setNewItemForm((f) => ({ ...f, expense_category: cats[0] }));
      }
      const accts = data.bank_accounts || [];
      setBankAccounts(accts);
      if (accts.length && !settleForm.bank_account_id) {
        setSettleForm((f) => ({ ...f, bank_account_id: accts[0].id }));
      }
      setLists(listsRes.data || []);

      if (!selectedTaskId && (data.tasks || []).length > 0) {
        setSelectedTaskId(data.tasks[0].id);
      }
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to load Daily Tasks", "error");
    } finally {
      setLoading(false);
    }
  }, [activeNav, selectedTaskId, newItemForm.expense_category, settleForm.bank_account_id]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const fetchComments = useCallback(async (taskId) => {
    if (!taskId) {
      setComments([]);
      return;
    }
    setLoadingComments(true);
    try {
      const { data } = await http.get(`/daily-tasks/${taskId}/comments`);
      setComments(data || []);
    } catch {
      setComments([]);
    } finally {
      setLoadingComments(false);
    }
  }, []);

  useEffect(() => {
    fetchComments(selectedTaskId);
    if (!selectedTaskId) return;
    const timer = setInterval(() => {
      http.get(`/daily-tasks/${selectedTaskId}/comments`).then(({ data }) => {
        setComments(data || []);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [selectedTaskId, fetchComments]);

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || null;
  const activeList = activeNav.startsWith("list:")
    ? lists.find((l) => l.id === activeNav.replace("list:", "")) || null
    : null;

  const handleQuickAddTask = async (e) => {
    e.preventDefault();
    if (!quickTitle.trim()) return;
    try {
      const { data } = await http.post("/daily-tasks", {
        title: quickTitle.trim(),
        priority: quickPriority,
        due_time: quickDueTime || "17:30",
        task_type: "staff_task",
        assignee_id: user?.id,
        assignee_name: user?.name || user?.email,
        approver_id: user?.id,
        approver_name: user?.name || user?.email,
      });
      setQuickTitle("");
      setSelectedTaskId(data.id);
      await fetchAll();
      showToast("Task added");
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to add task", "error");
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!taskForm.title.trim()) return;
    const assignee = users.find((u) => u.id === taskForm.assignee_id);
    const approver = users.find((u) => u.id === taskForm.approver_id);
    try {
      const { data } = await http.post("/daily-tasks", {
        ...taskForm,
        assignee_id: assignee?.id || user?.id,
        assignee_name: assignee?.name || user?.name || user?.email,
        assignee_role: assignee?.role || user?.role,
        approver_id: approver?.id || user?.id,
        approver_name: approver?.name || user?.name || user?.email,
        erp_ref_type: taskForm.erp_ref_type || null,
        erp_ref_label: taskForm.erp_ref_label || null,
      });
      setShowTaskModal(false);
      setTaskForm({
        title: "",
        description: "",
        task_type: "staff_task",
        priority: "P1",
        due_time: "17:30",
        assignee_id: "",
        approver_id: "",
        erp_ref_type: "",
        erp_ref_label: "",
        photos: [],
        voice_notes: [],
      });
      setSelectedTaskId(data.id);
      await fetchAll();
      showToast("Task assigned with Approver sign-off");
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to create task", "error");
    }
  };

  const handleStatusChange = async (taskId, status, extra = {}) => {
    try {
      await http.patch(`/daily-tasks/${taskId}/status`, { status, ...extra });
      await fetchAll();
      await fetchComments(taskId);
      const labels = {
        pending_approval: "Marked Done — awaiting Approver sign-off",
        done: "Approved & Closed (thread locked)",
        reopened: "Task Reopened",
        needs_input: "Flagged as Needs Partner Input",
        carried_forward: "Carried forward to tomorrow as P0",
      };
      showToast(labels[status] || "Status updated");
    } catch (err) {
      showToast(err?.response?.data?.detail || "Action not permitted", "error");
    }
  };

  const handlePhotoUpload = async (e, target = "comment") => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await http.post("/upload-image", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const url = data?.url || data?.image_url;
      if (url) {
        const photoObj = { url, caption: file.name };
        if (target === "task") {
          setTaskForm((f) => ({ ...f, photos: [...f.photos, photoObj] }));
        } else {
          setPendingPhotos((prev) => [...prev, photoObj]);
        }
      }
    } catch {
      showToast("Photo upload failed", "error");
    } finally {
      e.target.value = "";
    }
  };

  const uploadVoiceBlob = async (blobOrFile, filename, dur, target) => {
    const fd = new FormData();
    fd.append("file", blobOrFile, filename);
    try {
      const { data } = await http.post("/daily-tasks/upload-audio", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const voiceObj = { url: data.url, duration_sec: dur, mime_type: data.mime_type || blobOrFile.type || "audio/webm" };
      if (target === "task") {
        setTaskForm((f) => ({ ...f, voice_notes: [...f.voice_notes, voiceObj] }));
      } else {
        setPendingVoices((prev) => [...prev, voiceObj]);
      }
      showToast("Voice note attached");
    } catch {
      showToast("Voice upload failed", "error");
    }
  };

  const handleAudioFileFallback = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadVoiceBlob(file, file.name || "voice-note.m4a", 0, audioFileTargetRef.current);
    e.target.value = "";
  };

  const startVoiceRecording = async (target = "comment") => {
    // On mobile over plain HTTP (e.g. http://192.168.x.x), browsers disable navigator.mediaDevices.
    // Fall back to native mobile audio recorder / file input.
    if (typeof navigator === "undefined" || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      audioFileTargetRef.current = target;
      audioFileInputRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recordStartRef.current = Date.now();
      mr.ondataavailable = (ev) => {
        if (ev.data.size > 0) audioChunksRef.current.push(ev.data);
      };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const mime = mr.mimeType || "audio/webm";
        const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(audioChunksRef.current, { type: mime });
        const dur = Math.max(1, Math.round((Date.now() - recordStartRef.current) / 1000));
        await uploadVoiceBlob(blob, `voice-note.${ext}`, dur, target);
      };
      mediaRecorderRef.current = mr;
      mr.start();
      setRecording(true);
      setRecordingTarget(target);
    } catch {
      // If mic permission fails or is blocked, offer native audio file capture fallback
      audioFileTargetRef.current = target;
      audioFileInputRef.current?.click();
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
      setRecordingTarget(null);
    }
  };

  const handleSendComment = async (e) => {
    e.preventDefault();
    if (!selectedTask) return;
    if (!msgText.trim() && pendingPhotos.length === 0 && pendingVoices.length === 0) return;
    try {
      await http.post(`/daily-tasks/${selectedTask.id}/comments`, {
        message: msgText.trim(),
        photos: pendingPhotos,
        voice_notes: pendingVoices,
      });
      setMsgText("");
      setPendingPhotos([]);
      setPendingVoices([]);
      await fetchComments(selectedTask.id);
    } catch (err) {
      showToast(err?.response?.data?.detail || "Cannot send message", "error");
    }
  };

  // Shopping Lists handlers
  const handleCreateList = async (e) => {
    e.preventDefault();
    if (!newListForm.title.trim()) return;
    try {
      const { data } = await http.post("/daily-lists", newListForm);
      setShowListModal(false);
      setNewListForm({ title: "", list_type: "shopping" });
      await fetchAll();
      setActiveNav(`list:${data.id}`);
      showToast(`Created list "${data.title}"`);
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to create list", "error");
    }
  };

  const handleAddListItem = async (e) => {
    e.preventDefault();
    if (!activeList || !newItemForm.text.trim()) return;
    try {
      await http.post(`/daily-lists/${activeList.id}/items`, {
        text: newItemForm.text.trim(),
        qty: newItemForm.qty.trim(),
        expense_category: newItemForm.expense_category,
        estimated_amount: Number(newItemForm.actual_amount || 0),
        actual_amount: Number(newItemForm.actual_amount || 0),
        shop_note: newItemForm.shop_note.trim(),
      });
      setNewItemForm((f) => ({ ...f, text: "", qty: "", actual_amount: "", shop_note: "" }));
      await fetchAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to add item", "error");
    }
  };

  const handleToggleListItem = async (item) => {
    if (!activeList) return;
    try {
      await http.patch(`/daily-lists/${activeList.id}/items/${item.id}`, {
        done: !item.done,
      });
      await fetchAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || "Update failed", "error");
    }
  };

  const handleDeleteListItem = async (itemId) => {
    if (!activeList) return;
    try {
      await http.delete(`/daily-lists/${activeList.id}/items/${itemId}`);
      await fetchAll();
    } catch {
      showToast("Failed to delete item", "error");
    }
  };

  const handleConfirmSettle = async (e) => {
    e.preventDefault();
    if (!activeList || !settleForm.bank_account_id) return;
    setSettling(true);
    try {
      const { data } = await http.post(`/daily-lists/${activeList.id}/settle`, {
        settlement_mode: settleForm.settlement_mode,
        bank_account_id: settleForm.bank_account_id,
        payee: settleForm.payee || activeList.title,
        notes: settleForm.notes,
      });
      setShowSettleModal(false);
      await fetchAll();
      showToast(
        `Settled ${inr(data.settlement.total_amount)} (${data.settlement.item_count} items) → Synced to Expenses & Bank Reconciliation`
      );
    } catch (err) {
      showToast(err?.response?.data?.detail || "Settlement failed", "error");
    } finally {
      setSettling(false);
    }
  };

  const activeTasks = tasks.filter((t) => t.status !== "done");
  const completedTasks = tasks.filter((t) => t.status === "done");
  const unsettledBoughtItems = (activeList?.items || []).filter((i) => i.done && !i.settled);
  const unsettledTotal = unsettledBoughtItems.reduce(
    (sum, i) => sum + Number(i.actual_amount || i.estimated_amount || 0),
    0
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-slate-500 gap-2">
        <Loader2 className="w-5 h-5 animate-spin text-[#C27842]" />
        <span>Loading Daily Tasks &amp; Shopping Lists...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <input
        ref={audioFileInputRef}
        type="file"
        accept="audio/*,.m4a,.mp3,.wav,.ogg,.aac,.amr"
        onChange={handleAudioFileFallback}
        className="hidden"
      />
      {/* Feedback Banner */}
      {banner && (
        <div
          className={`px-4 py-2.5 rounded-xl text-xs font-medium flex items-center justify-between border ${
            banner.type === "error"
              ? "bg-rose-50 text-rose-700 border-rose-200"
              : "bg-emerald-50 text-emerald-700 border-emerald-200"
          }`}
        >
          <span>{banner.text}</span>
          <button onClick={() => setBanner(null)} className="opacity-60 hover:opacity-100">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Top KPI & Action Bar */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div>
            <span className="text-slate-500">Today&apos;s Completion: </span>
            <strong className="text-[#0F172A]">{summary.completion_pct || 0}%</strong>
            <span className="text-slate-400 ml-1">
              ({summary.done_today || 0}/{summary.total_today || 0})
            </span>
          </div>
          {summary.pending_approval_count > 0 && (
            <button
              onClick={() => setActiveNav("approvals")}
              className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200 font-semibold"
            >
              🛡️ {summary.pending_approval_count} Pending Approval
            </button>
          )}
          {summary.needs_input_count > 0 && (
            <button
              onClick={() => setActiveNav("needs_input")}
              className="px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-semibold"
            >
              ↩ {summary.needs_input_count} Needs Partner Input
            </button>
          )}
          {summary.carried_forward_count > 0 && (
            <span className="px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-semibold">
              🔥 {summary.carried_forward_count} Carried Forward (P0)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowListModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700"
          >
            <ShoppingCart className="w-3.5 h-3.5 text-[#C27842]" />
            + New List
          </button>
          <button
            onClick={() => setShowTaskModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#C27842] hover:bg-[#a96331] text-white text-xs font-semibold shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            Assign Task
          </button>
        </div>
      </div>

      {/* Mobile Horizontal Filter & Shopping Lists Bar */}
      <div className="lg:hidden flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
        {[
          { id: "today", label: "Today" },
          { id: "all", label: "All" },
          { id: "approvals", label: `Approvals${summary.pending_approval_count ? ` (${summary.pending_approval_count})` : ""}` },
          { id: "needs_input", label: `Input${summary.needs_input_count ? ` (${summary.needs_input_count})` : ""}` },
          { id: "history", label: "Closed" },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => {
              setActiveNav(item.id);
              setMobileDetailOpen(false);
            }}
            className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold border transition ${
              activeNav === item.id
                ? "bg-[#0F172A] text-white border-[#0F172A]"
                : "bg-white text-slate-700 border-slate-200"
            }`}
          >
            {item.label}
          </button>
        ))}
        {lists.map((l) => (
          <button
            key={l.id}
            onClick={() => {
              setActiveNav(`list:${l.id}`);
              setMobileDetailOpen(false);
            }}
            className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold border transition ${
              activeNav === `list:${l.id}`
                ? "bg-[#C27842] text-white border-[#C27842]"
                : "bg-white text-slate-700 border-slate-200"
            }`}
          >
            🛒 {l.title} ({(l.items || []).length})
          </button>
        ))}
      </div>

      {/* Todoist-Style 3-Pane Workspace */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-[620px]">
        {/* LEFT PANE: Filters & Custom Shopping Lists (Desktop) */}
        <aside className="hidden lg:block lg:col-span-3 border-r border-slate-200 bg-slate-50/70 p-3 space-y-5">
          <div className="space-y-1">
            {[
              { id: "today", label: "Today", icon: Calendar },
              { id: "all", label: "All Active Tasks", icon: Inbox },
              { id: "approvals", label: "Pending Approval", icon: ShieldCheck, badge: summary.pending_approval_count },
              { id: "needs_input", label: "Needs Partner Input", icon: AlertTriangle, badge: summary.needs_input_count },
              { id: "history", label: "Completed History", icon: History },
            ].map((item) => {
              const Icon = item.icon;
              const active = activeNav === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveNav(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition ${
                    active ? "bg-[#0F172A] text-white shadow-sm" : "text-slate-700 hover:bg-slate-200/70"
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </span>
                  {item.badge > 0 && (
                    <span
                      className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                        active ? "bg-[#C27842] text-white" : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Custom Shopping & Quick Lists */}
          <div>
            <div className="flex items-center justify-between px-2 mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Shopping &amp; Quick Lists
              </span>
              <button
                onClick={() => setShowListModal(true)}
                className="w-5 h-5 rounded flex items-center justify-center text-[#C27842] hover:bg-[#C27842]/10"
                title="Create new list"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-1">
              {lists.length === 0 && (
                <div className="px-2 py-2 text-[11px] text-slate-400">
                  No custom lists yet. Click + to create one.
                </div>
              )}
              {lists.map((l) => {
                const active = activeNav === `list:${l.id}`;
                const totalCount = (l.items || []).length;
                return (
                  <button
                    key={l.id}
                    onClick={() => setActiveNav(`list:${l.id}`)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition ${
                      active
                        ? "bg-[#C27842]/15 text-[#C27842] font-semibold border border-[#C27842]/30"
                        : "text-slate-700 hover:bg-slate-200/70"
                    }`}
                  >
                    <span className="flex items-center gap-2 truncate">
                      {l.list_type === "shopping" ? (
                        <ShoppingCart className="w-3.5 h-3.5 shrink-0" />
                      ) : (
                        <ListTodo className="w-3.5 h-3.5 shrink-0" />
                      )}
                      <span className="truncate">{l.title}</span>
                    </span>
                    <span className="text-[11px] opacity-60">{totalCount}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        {/* CENTER PANE: Either Shopping List View OR Task List View */}
        {activeList ? (
          <main className="lg:col-span-9 p-5 flex flex-col gap-4 overflow-y-auto">
            {/* List Header + Settlement Summary */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-[#0F172A] flex items-center gap-2">
                  <ShoppingCart className="w-4 h-4 text-[#C27842]" />
                  {activeList.title}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Assign ERP Expense Categories to each item, check off as bought, then Transfer or Withdraw the summed total from a listed bank account.
                </p>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <div className="text-[11px] text-slate-500">Bought &amp; Unsettled Total</div>
                  <div className="text-lg font-extrabold text-[#0F172A]">{inr(unsettledTotal)}</div>
                </div>
                <button
                  disabled={unsettledTotal <= 0}
                  onClick={() => {
                    setSettleForm((f) => ({ ...f, payee: activeList.title }));
                    setShowSettleModal(true);
                  }}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-xs font-semibold shadow-sm"
                >
                  <Landmark className="w-4 h-4" />
                  Settle Total → Bank Sync
                </button>
              </div>
            </div>

            {/* Add Item Form */}
            <form onSubmit={handleAddListItem} className="grid grid-cols-1 md:grid-cols-12 gap-2 bg-white border border-slate-200 rounded-xl p-3">
              <input
                type="text"
                required
                placeholder="Item name (e.g., PU Adhesive 20L)"
                value={newItemForm.text}
                onChange={(e) => setNewItemForm((f) => ({ ...f, text: e.target.value }))}
                className="md:col-span-4 px-3 py-1.5 text-xs rounded-lg border border-slate-300"
              />
              <input
                type="text"
                placeholder="Qty (e.g., 2 drums)"
                value={newItemForm.qty}
                onChange={(e) => setNewItemForm((f) => ({ ...f, qty: e.target.value }))}
                className="md:col-span-2 px-2.5 py-1.5 text-xs rounded-lg border border-slate-300"
              />
              <select
                value={newItemForm.expense_category}
                onChange={(e) => setNewItemForm((f) => ({ ...f, expense_category: e.target.value }))}
                className="md:col-span-3 px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 bg-white"
              >
                {expenseCategories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="₹ Amount"
                value={newItemForm.actual_amount}
                onChange={(e) => setNewItemForm((f) => ({ ...f, actual_amount: e.target.value }))}
                className="md:col-span-2 px-2.5 py-1.5 text-xs rounded-lg border border-slate-300"
              />
              <button
                type="submit"
                className="md:col-span-1 px-3 py-1.5 rounded-lg bg-[#0F172A] text-white text-xs font-semibold hover:bg-slate-800"
              >
                Add
              </button>
            </form>

            {/* Items List */}
            <div className="space-y-2">
              {(activeList.items || []).length === 0 && (
                <div className="text-center py-10 text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                  No items in this list yet. Add an item above with its ERP Expense Category.
                </div>
              )}
              {(activeList.items || []).map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-white hover:border-slate-300"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <button
                      type="button"
                      disabled={item.settled}
                      onClick={() => handleToggleListItem(item)}
                      className="text-[#C27842] disabled:opacity-60"
                    >
                      {item.done ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <Circle className="w-5 h-5" />}
                    </button>
                    <div className="min-w-0">
                      <div className={`text-xs font-semibold ${item.done ? "line-through text-slate-400" : "text-slate-900"}`}>
                        {item.text} {item.qty ? <span className="text-slate-500 font-normal">({item.qty})</span> : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mt-1">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-medium">
                          {item.expense_category}
                        </span>
                        {item.settled && (
                          <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-semibold">
                            ✓ Synced ({item.settlement_mode === "cash_withdrawal" ? "Cash Withdrawal" : "Bank Transfer"})
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs font-bold text-[#0F172A]">
                      {inr(item.actual_amount || item.estimated_amount || 0)}
                    </span>
                    {!item.settled && (
                      <button
                        onClick={() => handleDeleteListItem(item.id)}
                        className="text-slate-400 hover:text-rose-600"
                        title="Remove item"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Past Settlements History */}
            {(activeList.settlements || []).length > 0 && (
              <div className="pt-3 border-t border-slate-200 space-y-2">
                <div className="text-xs font-bold text-slate-600">Settlement History</div>
                {(activeList.settlements || []).map((s) => (
                  <div key={s.id} className="text-xs bg-emerald-50/70 border border-emerald-200 rounded-lg px-3 py-2 flex items-center justify-between">
                    <span>
                      <strong>{s.settlement_mode === "cash_withdrawal" ? "💵 Cash Withdrawal" : "💸 Bank Transfer"}</strong> from{" "}
                      <strong>{s.bank_account_name}</strong> ({s.item_count} items) on {s.date}
                    </span>
                    <strong className="text-emerald-700">{inr(s.total_amount)}</strong>
                  </div>
                ))}
              </div>
            )}
          </main>
        ) : (
          <>
            {/* CENTER PANE: Tasks */}
            <main className="lg:col-span-5 border-b lg:border-b-0 lg:border-r border-slate-200 p-4 flex flex-col gap-3 overflow-y-auto">
              {/* Inline Todoist-style Quick Add (Time-Bounded) */}
              <form onSubmit={handleQuickAddTask} className="flex flex-wrap items-center gap-1.5">
                <input
                  type="text"
                  placeholder="+ Quick add task for today (Press Enter)..."
                  value={quickTitle}
                  onChange={(e) => setQuickTitle(e.target.value)}
                  className="flex-1 min-w-[160px] px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:border-[#C27842]"
                />
                <input
                  type="time"
                  value={quickDueTime}
                  onChange={(e) => setQuickDueTime(e.target.value)}
                  title="Due time (time-bound)"
                  className="px-2 py-2 text-xs rounded-lg border border-slate-300 bg-white text-slate-700"
                />
                <select
                  value={quickPriority}
                  onChange={(e) => setQuickPriority(e.target.value)}
                  title="Priority"
                  className="px-2 py-2 text-xs rounded-lg border border-slate-300 bg-white text-slate-700 font-semibold"
                >
                  <option value="P0">P0</option>
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                </select>
                <button
                  type="submit"
                  className="px-3 py-2 rounded-lg bg-[#0F172A] text-white text-xs font-semibold hover:bg-slate-800"
                >
                  Add
                </button>
              </form>

              {/* Active Tasks */}
              <div className="space-y-2">
                {activeTasks.length === 0 && (
                  <div className="text-center py-10 text-xs text-slate-400">
                    No active tasks in this view.
                  </div>
                )}
                {activeTasks.map((task) => {
                  const pStyle = PRIORITY_STYLES[task.priority] || PRIORITY_STYLES.P1;
                  const isSelected = task.id === selectedTaskId;
                  return (
                    <div
                      key={task.id}
                      onClick={() => {
                        setSelectedTaskId(task.id);
                        setMobileDetailOpen(true);
                      }}
                      className={`p-3.5 lg:p-3 rounded-xl border cursor-pointer transition ${
                        isSelected
                          ? "border-[#C27842] bg-[#C27842]/5 shadow-xs"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-start gap-2.5">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStatusChange(task.id, "pending_approval");
                          }}
                          className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${pStyle.ring}`}
                          title="Mark Done (sends to Approver)"
                        >
                          {task.status === "pending_approval" && <Check className="w-2.5 h-2.5" />}
                        </button>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold text-[#0F172A] flex items-center gap-1.5 flex-wrap">
                            <span>{task.title}</span>
                            {task.carry_forward_count > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[10px] font-bold">
                                Carried ({task.carry_forward_count}x)
                              </span>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] text-slate-500">
                            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${pStyle.badge}`}>
                              {task.priority}
                            </span>
                            <span className="inline-flex items-center gap-1">
                              <Clock className="w-3 h-3" /> {task.due_time || "17:30"}
                            </span>
                            {(() => {
                              const now = new Date();
                              const todayIso = now.toISOString().slice(0, 10);
                              const hhmm = now.toTimeString().slice(0, 5);
                              const isOverdue =
                                task.status !== "done" &&
                                task.task_date &&
                                (task.task_date < todayIso || (task.task_date === todayIso && (task.due_time || "17:30") < hhmm));
                              return isOverdue ? (
                                <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-semibold">
                                  Overdue
                                </span>
                              ) : null;
                            })()}
                            <span>→ {task.assignee_name}</span>
                            <span className="text-slate-400">• Approver: {task.approver_name}</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedTaskId(task.id);
                                setMobileDetailOpen(true);
                              }}
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 hover:bg-[#C27842]/15 text-slate-700 hover:text-[#C27842] font-medium"
                              title="Open task messaging"
                            >
                              <MessageSquare className="w-3 h-3" />
                              {task.comment_count || 0}
                            </button>
                          </div>
                          {task.status === "pending_approval" && (
                            <div className="mt-1.5 inline-block px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-semibold">
                              🛡️ Pending Approver Sign-Off
                            </div>
                          )}
                          {task.status === "needs_input" && (
                            <div className="mt-1.5 inline-block px-2 py-0.5 rounded bg-rose-100 text-rose-700 text-[10px] font-semibold">
                              ↩ Needs Partner Input
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Collapsible Completed Tasks */}
              {completedTasks.length > 0 && (
                <div className="pt-2 border-t border-slate-200">
                  <button
                    onClick={() => setShowCompletedDrawer((v) => !v)}
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800"
                  >
                    {showCompletedDrawer ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    Completed &amp; Closed ({completedTasks.length})
                  </button>
                  {showCompletedDrawer && (
                    <div className="mt-2 space-y-1.5">
                      {completedTasks.map((task) => (
                        <div
                          key={task.id}
                          onClick={() => {
                            setSelectedTaskId(task.id);
                            setMobileDetailOpen(true);
                          }}
                          className={`px-3 py-2.5 lg:py-2 rounded-lg border text-xs cursor-pointer flex items-center justify-between ${
                            task.id === selectedTaskId ? "border-[#C27842] bg-slate-50" : "border-slate-200 bg-slate-50/50"
                          }`}
                        >
                          <span className="line-through text-slate-500 truncate">{task.title}</span>
                          <span className="text-[10px] text-emerald-700 font-semibold shrink-0 ml-2">✓ Closed</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </main>

            {/* RIGHT PANE: Task Detail, Approver Sign-Off & Closed Thread Lock (Full-screen Sheet on Mobile) */}
            <section
              ref={detailPaneRef}
              className={`${
                mobileDetailOpen ? "fixed inset-0 z-50 bg-white flex flex-col" : "hidden"
              } lg:static lg:flex lg:col-span-4 lg:flex-col justify-between lg:bg-slate-50/40 p-4`}
            >
              {/* Mobile Back Header */}
              <div className="lg:hidden flex items-center justify-between pb-3 mb-3 border-b border-slate-200 shrink-0">
                <button
                  type="button"
                  onClick={() => setMobileDetailOpen(false)}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-[#0F172A]"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Tasks
                </button>
                <span className="text-[11px] text-slate-400 font-medium">Task Details &amp; Chat</span>
              </div>
              {selectedTask ? (
                <>
                  <div className="space-y-3 overflow-y-auto flex-1 lg:max-h-[460px] pr-1">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-bold text-[#0F172A]">{selectedTask.title}</h3>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Assignee: <strong>{selectedTask.assignee_name}</strong> • Approver:{" "}
                          <strong>{selectedTask.approver_name}</strong>
                        </p>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 text-slate-700 uppercase">
                        {selectedTask.status.replace("_", " ")}
                      </span>
                    </div>

                    {selectedTask.description && (
                      <div className="p-2.5 rounded-lg bg-white border border-slate-200 text-xs text-slate-700">
                        {selectedTask.description}
                      </div>
                    )}

                    {((selectedTask.photos || []).length > 0 || (selectedTask.voice_notes || []).length > 0) && (
                      <div className="p-2.5 rounded-lg bg-white border border-slate-200 space-y-2">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Task Attachments
                        </div>
                        {(selectedTask.photos || []).map((p, idx) => (
                          <img
                            key={idx}
                            src={resolveMediaUrl(p.url)}
                            alt={p.caption || "Task photo"}
                            className="rounded-lg max-h-36 object-cover border border-slate-200"
                          />
                        ))}
                        {(selectedTask.voice_notes || []).map((v, idx) => (
                          <audio key={idx} controls src={resolveMediaUrl(v.url)} className="w-full h-8" />
                        ))}
                      </div>
                    )}

                    {/* Workflow Action Buttons */}
                    <div className="flex flex-wrap gap-1.5">
                      {selectedTask.status !== "done" ? (
                        <>
                          {selectedTask.status !== "pending_approval" && (
                            <button
                              onClick={() => handleStatusChange(selectedTask.id, "pending_approval")}
                              className="px-2.5 py-1.5 rounded-lg bg-[#0F172A] text-white text-[11px] font-semibold"
                            >
                              Mark Done (For Approval)
                            </button>
                          )}
                          <button
                            onClick={() => handleStatusChange(selectedTask.id, "done")}
                            className="px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white text-[11px] font-semibold"
                          >
                            ✓ Approve &amp; Close
                          </button>
                          <button
                            onClick={() => handleStatusChange(selectedTask.id, "needs_input")}
                            className="px-2.5 py-1.5 rounded-lg bg-rose-50 text-rose-700 border border-rose-200 text-[11px] font-semibold"
                          >
                            ↩ Needs Input
                          </button>
                          <button
                            onClick={() => setCarryTask(selectedTask)}
                            className="px-2.5 py-1.5 rounded-lg bg-white text-slate-700 border border-slate-300 text-[11px] font-semibold"
                          >
                            Not Done Today
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => handleStatusChange(selectedTask.id, "reopened")}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-100 text-amber-900 border border-amber-300 text-[11px] font-semibold"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          Reopen Task &amp; Thread
                        </button>
                      )}
                    </div>

                    {/* Comments Thread */}
                    <div className="pt-2 border-t border-slate-200 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <MessageSquare className="w-3.5 h-3.5 text-[#C27842]" />
                          Task Messaging ({comments.length})
                        </span>
                        {selectedTask.status !== "done" && (
                          <span className="text-[10px] text-emerald-600 font-medium">● Live</span>
                        )}
                      </div>
                      {loadingComments ? (
                        <div className="text-xs text-slate-400">Loading messages...</div>
                      ) : comments.length === 0 ? (
                        <div className="text-xs text-slate-400">No messages yet.</div>
                      ) : (
                        comments.map((c) => {
                          const isMine = !c.is_system && String(c.author_id) === String(user?.id);
                          return (
                          <div
                            key={c.id}
                            className={`p-2.5 rounded-xl text-xs border ${
                              c.is_system
                                ? "bg-slate-100 border-slate-200 text-slate-600 italic"
                                : isMine
                                ? "bg-[#C27842]/10 border-[#C27842]/30 text-slate-900"
                                : "bg-white border-slate-200 text-slate-800"
                            }`}
                          >
                            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                              <strong className="text-slate-700">{c.author_name}</strong>
                              <span>{new Date(c.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                            </div>
                            {c.message && <div>{c.message}</div>}
                            {(c.photos || []).map((p, idx) => (
                              <img
                                key={idx}
                                src={resolveMediaUrl(p.url)}
                                alt={p.caption || "Task attachment"}
                                className="mt-1.5 rounded-lg max-h-36 object-cover border border-slate-200"
                              />
                            ))}
                            {(c.voice_notes || []).map((v, idx) => (
                              <audio key={idx} controls src={resolveMediaUrl(v.url)} className="mt-1.5 w-full h-8" />
                            ))}
                          </div>
                        );})
                      )}
                      <div ref={threadEndRef} />
                    </div>
                  </div>

                  {/* Composer or Closed Lock */}
                  <div className="pt-3 border-t border-slate-200 mt-3">
                    {selectedTask.status === "done" ? (
                      <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-100 border border-slate-200 text-xs text-slate-600">
                        <Lock className="w-4 h-4 text-slate-500 shrink-0" />
                        <span>
                          Task is <strong>Closed</strong>. Messaging is disabled until reopened.
                        </span>
                      </div>
                    ) : (
                      <form onSubmit={handleSendComment} className="space-y-2">
                        {(pendingPhotos.length > 0 || pendingVoices.length > 0) && (
                          <div className="flex flex-wrap gap-1.5 text-[11px]">
                            {pendingPhotos.map((p, i) => (
                              <span key={i} className="px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
                                📷 {p.caption || "Photo"}
                              </span>
                            ))}
                            {pendingVoices.map((v, i) => (
                              <span key={i} className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                                🎙️ Voice ({v.duration_sec}s)
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="flex items-center gap-1.5">
                          <label className="p-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 cursor-pointer text-slate-600" title="Attach Photo">
                            <Camera className="w-4 h-4" />
                            <input type="file" accept="image/*" onChange={(e) => handlePhotoUpload(e, "comment")} className="hidden" />
                          </label>
                          <button
                            type="button"
                            onClick={recording && recordingTarget === "comment" ? stopVoiceRecording : () => startVoiceRecording("comment")}
                            className={`p-2 rounded-lg border text-xs ${
                              recording && recordingTarget === "comment"
                                ? "bg-rose-600 text-white border-rose-600 animate-pulse"
                                : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                            }`}
                            title={recording && recordingTarget === "comment" ? "Stop Recording" : "Record Voice Note"}
                          >
                            {recording && recordingTarget === "comment" ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                          </button>
                          <input
                            type="text"
                            placeholder="Write message or update..."
                            value={msgText}
                            onChange={(e) => setMsgText(e.target.value)}
                            className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-slate-300 bg-white"
                          />
                          <button
                            type="submit"
                            className="p-2 rounded-lg bg-[#C27842] hover:bg-[#a96331] text-white"
                            title="Send"
                          >
                            <Send className="w-4 h-4" />
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-xs text-slate-400">
                  Select a task to view details, approver sign-off, and thread.
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {/* MODAL: Assign Task */}
      {showTaskModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <form onSubmit={handleCreateTask} className="bg-white rounded-2xl max-w-md w-full p-5 space-y-3 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-[#0F172A]">Assign Task / Partner To-Do</h3>
              <button type="button" onClick={() => setShowTaskModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              required
              placeholder="Task title (e.g., Inspect PU Sole Batch #42)"
              value={taskForm.title}
              onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300"
            />
            <textarea
              rows={2}
              placeholder="Instructions / details..."
              value={taskForm.description}
              onChange={(e) => setTaskForm((f) => ({ ...f, description: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300"
            />
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Priority</label>
                <select
                  value={taskForm.priority}
                  onChange={(e) => setTaskForm((f) => ({ ...f, priority: e.target.value }))}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
                >
                  <option value="P0">P0 — Urgent</option>
                  <option value="P1">P1 — High</option>
                  <option value="P2">P2 — Normal</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Due Time</label>
                <input
                  type="time"
                  value={taskForm.due_time}
                  onChange={(e) => setTaskForm((f) => ({ ...f, due_time: e.target.value }))}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-300"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Assign To</label>
                <select
                  value={taskForm.assignee_id}
                  onChange={(e) => setTaskForm((f) => ({ ...f, assignee_id: e.target.value }))}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
                >
                  <option value="">Myself ({user?.name || "Current User"})</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.role})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Approver (Before Close)</label>
                <select
                  value={taskForm.approver_id}
                  onChange={(e) => setTaskForm((f) => ({ ...f, approver_id: e.target.value }))}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
                >
                  <option value="">Myself ({user?.name || "Owner"})</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.role})
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="space-y-2 pt-1">
              <div className="flex items-center gap-2 text-xs">
                <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 cursor-pointer text-slate-700 font-medium">
                  <Camera className="w-3.5 h-3.5 text-[#C27842]" />
                  <span>Attach Photo</span>
                  <input type="file" accept="image/*" onChange={(e) => handlePhotoUpload(e, "task")} className="hidden" />
                </label>
                <button
                  type="button"
                  onClick={recording && recordingTarget === "task" ? stopVoiceRecording : () => startVoiceRecording("task")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium ${
                    recording && recordingTarget === "task"
                      ? "bg-rose-600 text-white border-rose-600 animate-pulse"
                      : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {recording && recordingTarget === "task" ? <Square className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5 text-[#C27842]" />}
                  <span>{recording && recordingTarget === "task" ? "Stop Recording" : "Record Voice Note"}</span>
                </button>
              </div>
              {(taskForm.photos.length > 0 || taskForm.voice_notes.length > 0) && (
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  {taskForm.photos.map((p, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
                      📷 {p.caption || "Photo"}
                      <button
                        type="button"
                        onClick={() => setTaskForm((f) => ({ ...f, photos: f.photos.filter((_, idx) => idx !== i) }))}
                        className="hover:text-rose-600 font-bold"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {taskForm.voice_notes.map((v, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                      🎙️ Voice ({v.duration_sec}s)
                      <button
                        type="button"
                        onClick={() => setTaskForm((f) => ({ ...f, voice_notes: f.voice_notes.filter((_, idx) => idx !== i) }))}
                        className="hover:text-rose-600 font-bold"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowTaskModal(false)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs">
                Cancel
              </button>
              <button type="submit" className="px-4 py-1.5 rounded-lg bg-[#C27842] text-white text-xs font-semibold">
                Create Task
              </button>
            </div>
          </form>
        </div>
      )}

      {/* MODAL: Non-Completion Reason -> Carry Forward */}
      {carryTask && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-5 space-y-3 shadow-xl">
            <h3 className="text-sm font-bold text-[#0F172A]">Log Non-Completion Reason</h3>
            <p className="text-xs text-slate-500">
              &quot;{carryTask.title}&quot; will be carried forward to tomorrow as <strong>P0 Urgent</strong>.
            </p>
            <select
              value={carryReason.category}
              onChange={(e) => setCarryReason((r) => ({ ...r, category: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 bg-white"
            >
              {NON_COMPLETION_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <textarea
              rows={2}
              placeholder="Explain why it was not completed today..."
              value={carryReason.note}
              onChange={(e) => setCarryReason((r) => ({ ...r, note: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setCarryTask(null)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs">
                Cancel
              </button>
              <button
                onClick={async () => {
                  await handleStatusChange(carryTask.id, "carried_forward", {
                    non_completion_reason: carryReason,
                  });
                  setCarryTask(null);
                }}
                className="px-4 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold"
              >
                Carry Forward as P0
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Create Custom List */}
      {showListModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <form onSubmit={handleCreateList} className="bg-white rounded-2xl max-w-sm w-full p-5 space-y-3 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-[#0F172A]">Create New List</h3>
              <button type="button" onClick={() => setShowListModal(false)} className="text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              required
              placeholder="List name (can be anything)..."
              value={newListForm.title}
              onChange={(e) => setNewListForm((f) => ({ ...f, title: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300"
            />
            <select
              value={newListForm.list_type}
              onChange={(e) => setNewListForm((f) => ({ ...f, list_type: e.target.value }))}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 bg-white"
            >
              <option value="shopping">🛒 Shopping List (Linked to Expenses &amp; Bank)</option>
              <option value="checklist">📋 Quick Checklist</option>
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowListModal(false)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs">
                Cancel
              </button>
              <button type="submit" className="px-4 py-1.5 rounded-lg bg-[#C27842] text-white text-xs font-semibold">
                Create List
              </button>
            </div>
          </form>
        </div>
      )}

      {/* MODAL: Settle Shopping List Total -> Transfer or Withdraw from Bank */}
      {showSettleModal && activeList && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <form onSubmit={handleConfirmSettle} className="bg-white rounded-2xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-[#0F172A]">Settle List Total &amp; Sync ERP</h3>
              <button type="button" onClick={() => setShowSettleModal(false)} className="text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
              <span className="text-xs text-slate-600">
                Summed Total ({unsettledBoughtItems.length} bought items)
              </span>
              <span className="text-lg font-extrabold text-[#0F172A]">{inr(unsettledTotal)}</span>
            </div>

            <div className="space-y-1.5 text-xs">
              <label className="block font-semibold text-slate-700">Settlement Action</label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex items-center gap-2 p-2.5 rounded-lg border border-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="settlement_mode"
                    checked={settleForm.settlement_mode === "bank_transfer"}
                    onChange={() => setSettleForm((f) => ({ ...f, settlement_mode: "bank_transfer" }))}
                  />
                  <ArrowRightLeft className="w-3.5 h-3.5 text-[#C27842]" />
                  <span>Transfer Money</span>
                </label>
                <label className="flex items-center gap-2 p-2.5 rounded-lg border border-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="settlement_mode"
                    checked={settleForm.settlement_mode === "cash_withdrawal"}
                    onChange={() => setSettleForm((f) => ({ ...f, settlement_mode: "cash_withdrawal" }))}
                  />
                  <Banknote className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Withdraw Cash</span>
                </label>
              </div>
            </div>

            <div className="space-y-1.5 text-xs">
              <label className="block font-semibold text-slate-700">Listed Bank Account</label>
              <select
                required
                value={settleForm.bank_account_id}
                onChange={(e) => setSettleForm((f) => ({ ...f, bank_account_id: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white"
              >
                {bankAccounts.length === 0 && <option value="">No active bank accounts found</option>}
                {bankAccounts.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name || b.bank_name} — Bal: {inr(b.current_balance || 0)}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5 text-xs">
              <label className="block font-semibold text-slate-700">Payee / Recipient</label>
              <input
                type="text"
                value={settleForm.payee}
                onChange={(e) => setSettleForm((f) => ({ ...f, payee: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-slate-300"
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setShowSettleModal(false)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs">
                Cancel
              </button>
              <button
                type="submit"
                disabled={settling || !settleForm.bank_account_id}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-xs font-semibold"
              >
                {settling ? "Syncing..." : "Confirm & Post to ERP"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
