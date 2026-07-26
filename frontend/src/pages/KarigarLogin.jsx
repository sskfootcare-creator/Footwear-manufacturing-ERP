import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError } from "@/lib/api";
import { Delete, Loader2, HardHat } from "lucide-react";

const DIGITS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

export default function KarigarLogin() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("phone"); // "phone" | "pin"
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleKey = useCallback(
    (key) => {
      if (key === "⌫") {
        if (step === "phone") setPhone((p) => p.slice(0, -1));
        else setPin((p) => p.slice(0, -1));
        return;
      }
      if (!key) return;
      if (step === "phone") {
        setPhone((p) => (p.length < 10 ? p + key : p));
      } else {
        setPin((p) => (p.length < 6 ? p + key : p));
      }
    },
    [step]
  );

  const handleKeyTouch = (e, d) => {
    if (e.type === "touchstart") {
      e.preventDefault();
    }
    handleKey(d);
  };

  const handlePhoneNext = () => {
    if (phone.length < 10) {
      setError("Please enter your 10-digit mobile number");
      return;
    }
    setError("");
    setStep("pin");
  };

  const handleLogin = async () => {
    if (pin.length < 4) {
      setError("PIN must be at least 4 digits");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const { data } = await http.post("/auth/worker-login", { phone, pin });
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("karigar_token", data.access_token);
        localStorage.setItem("karigar_worker", JSON.stringify({
          worker_id: data.worker_id,
          name: data.name,
          skill: data.skill,
          role: "worker",
        }));
      }
      navigate("/karigar", { replace: true });
    } catch (e) {
      setError(friendlyAxiosError(e));
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  const handleEnter = step === "phone" ? handlePhoneNext : handleLogin;

  const PinDots = ({ value, max }) => (
    <div style={{ display: "flex", gap: "12px", justifyContent: "center", margin: "16px 0" }}>
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          style={{
            width: 16, height: 16, borderRadius: "50%",
            border: "2px solid",
            borderColor: i < value.length ? "#f59e0b" : "#475569",
            background: i < value.length ? "#f59e0b" : "transparent",
            transform: i < value.length ? "scale(1.1)" : "scale(1)",
            transition: "all 0.15s ease",
          }}
        />
      ))}
    </div>
  );

  return (
    <div style={{
      minHeight: "100dvh",
      background: "linear-gradient(145deg, #0f172a 0%, #1e293b 60%, #172032 100%)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "1rem", fontFamily: "'Inter', 'Segoe UI', sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        .kl-key {
          background: rgba(51,65,85,0.7);
          border: 1px solid rgba(255,255,255,0.07);
          border-radius: 12px; height: 64px;
          display: flex; align-items: center; justify-content: center;
          font-size: 1.4rem; font-weight: 600; color: #e2e8f0;
          cursor: pointer; user-select: none;
          -webkit-user-select: none;
          -webkit-touch-callout: none;
          -webkit-tap-highlight-color: transparent;
          touch-action: manipulation;
          will-change: transform, background-color;
          transition: transform 0.1s ease, background-color 0.1s ease;
        }
        .kl-key:active {
          background: rgba(194,120,66,0.65) !important;
          transform: scale(0.95) !important;
        }
        .kl-btn { transition: all 0.2s ease; touch-action: manipulation; }
        .kl-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 10px 25px rgba(194,120,66,0.45) !important; }
        .kl-btn:active:not(:disabled) { transform: scale(0.98); }
      `}</style>

      <div style={{
        background: "rgba(30,41,59,0.85)", backdropFilter: "blur(16px)",
        border: "1px solid rgba(255,255,255,0.08)", borderRadius: 20,
        width: "100%", maxWidth: 360, padding: "2rem 1.5rem 1.5rem",
        boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
      }}>
        {/* Logo */}
        <div style={{
          width: 56, height: 56,
          background: "linear-gradient(135deg, #C27842, #a05a28)",
          borderRadius: 14, display: "flex", alignItems: "center",
          justifyContent: "center", margin: "0 auto 1rem",
          boxShadow: "0 8px 20px rgba(194,120,66,0.4)",
        }}>
          <HardHat size={28} color="white" />
        </div>
        <div style={{ textAlign: "center", color: "#f1f5f9", fontSize: "1.3rem", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 4 }}>
          SSK Karigar App
        </div>
        <div style={{ textAlign: "center", color: "#64748b", fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 24 }}>
          {step === "phone" ? "Enter your phone number" : "Enter your PIN"}
        </div>

        {/* Display area */}
        {step === "phone" ? (
          <>
            <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 6 }}>
              Mobile Number
            </div>
            <div style={{
              background: "rgba(15,23,42,0.6)", border: "1.5px solid rgba(255,255,255,0.1)",
              borderRadius: 10, padding: "0.75rem 1rem",
              fontSize: "1.4rem", fontWeight: 700, color: phone ? "#f1f5f9" : "#475569",
              letterSpacing: "0.12em", textAlign: "center", minHeight: 48,
            }}>
              {phone
                ? phone.replace(/(\d{5})(\d{0,5})/, "$1 $2").trim()
                : "_ _ _ _ _  _ _ _ _ _"}
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 4 }}>PIN</div>
            <PinDots value={pin} max={6} />
          </>
        )}

        {/* Keypad */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "0.6rem", marginTop: "1rem" }}>
          {DIGITS.map((d, i) => (
            d === "" ? (
              <div key={i} />
            ) : (
              <button
                key={i}
                className="kl-key"
                style={d === "⌫" ? { color: "#f87171" } : {}}
                onTouchStart={(e) => handleKeyTouch(e, d)}
                onClick={(e) => handleKeyTouch(e, d)}
                aria-label={d === "⌫" ? "Delete" : `Digit ${d}`}
                id={`kl-key-${d === "⌫" ? "del" : d}`}
              >
                {d === "⌫" ? <Delete size={20} /> : d}
              </button>
            )
          ))}
        </div>

        {/* Action */}
        <button
          className="kl-btn"
          style={{
            width: "100%", marginTop: "1rem",
            background: "linear-gradient(135deg, #C27842, #a05a28)",
            color: "white", border: "none", borderRadius: 12,
            height: 54, fontSize: "1rem", fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.65 : 1,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            boxShadow: "0 6px 18px rgba(194,120,66,0.35)",
          }}
          onClick={handleEnter}
          disabled={loading}
          id="kl-submit-btn"
        >
          {loading
            ? <Loader2 size={20} style={{ animation: "spin 1s linear infinite" }} />
            : step === "phone" ? "Continue →" : "Login"
          }
        </button>

        {error && (
          <div style={{
            background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 8, padding: "0.6rem 0.75rem", color: "#fca5a5",
            fontSize: "0.78rem", textAlign: "center", marginTop: 12,
          }} role="alert">
            {error}
          </div>
        )}

        {step === "pin" && !loading && (
          <button
            style={{
              background: "none", border: "none", color: "#64748b",
              fontSize: "0.8rem", cursor: "pointer", marginTop: 12,
              width: "100%", textAlign: "center", padding: "0.5rem",
            }}
            onClick={() => { setStep("phone"); setPin(""); setError(""); }}
            id="kl-back-btn"
          >
            ← Change number
          </button>
        )}

        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
