import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  Loader2,
  HardHat,
  Cpu,
  Layers,
  TrendingUp,
  CheckCircle2,
  ArrowRight,
  Factory,
  Building2,
  Sparkles,
  Lock,
  X,
  ChevronRight,
  Eye,
  EyeOff,
  ShoppingBag,
  Check,
  Send,
  BarChart3,
  RefreshCw,
  Menu,
  PhoneCall,
  FileSpreadsheet,
} from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, error } = useAuth();

  // Login form states
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);

  // Mobile navigation drawer state
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Modal Login state
  const [portalModalOpen, setPortalModalOpen] = useState(false);

  // Forgot password modal states
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotResult, setForgotResult] = useState(null);

  // B2B Contact inquiry state
  const [inquiryName, setInquiryName] = useState("");
  const [inquiryCompany, setInquiryCompany] = useState("");
  const [inquiryEmail, setInquiryEmail] = useState("");
  const [inquiryType, setInquiryType] = useState("Private Label / Contract Mfg");
  const [inquiryVolume, setInquiryVolume] = useState("1,000 - 5,000 pairs/month");
  const [inquiryMessage, setInquiryMessage] = useState("");
  const [inquirySuccess, setInquirySuccess] = useState(false);

  // Product visual modal state
  const [selectedProduct, setSelectedProduct] = useState(null);

  // Open portal modal if URL hash is #login or #signin
  useEffect(() => {
    if (location.hash === "#login" || location.hash === "#signin") {
      setPortalModalOpen(true);
    }
  }, [location.hash]);

  // Lock body scroll when mobile menu or modal is open
  useEffect(() => {
    if (mobileMenuOpen || portalModalOpen || forgotOpen || selectedProduct) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "auto";
    }
    return () => {
      document.body.style.overflow = "auto";
    };
  }, [mobileMenuOpen, portalModalOpen, forgotOpen, selectedProduct]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    await login(email, password);
    setBusy(false);
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setForgotBusy(true);
    setForgotResult(null);
    try {
      const { data } = await http.post("/auth/forgot-password", { email: forgotEmail });
      setForgotResult({
        message: data?.message || "If that email matches an account, a reset link has been sent.",
        dev_reset_url: data?.dev_reset_url || null,
        email_status: data?.email_status || null,
      });
    } catch (err) {
      setForgotResult({
        message:
          err.response?.data?.detail ||
          err.message ||
          "Could not send reset link. Please try again.",
      });
    } finally {
      setForgotBusy(false);
    }
  };

  const handleInquirySubmit = (e) => {
    e.preventDefault();
    setInquirySuccess(true);
  };

  const scrollToSection = (id) => {
    setMobileMenuOpen(false);
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const productList = [
    {
      id: "laser-cut",
      name: "Precision Laser-Cut Flat Sandal",
      category: "Flat Sandals & T-Straps",
      image: "/company/laser_cut_flat.jpg",
      materials: "Genuine Tan Crust Leather, Comfort Cushion Insole, Anti-Slip TPR Sole",
      features: "Geometric CNC laser perforation, hand-stitched welt, adjustable brass buckle.",
      productionCapacity: "12,000 pairs / month",
      channel: "B2B Private-Label & D2C Marketplaces (Myntra)",
    },
    {
      id: "braided-slide",
      name: "Hand-Braided Metallic Slip-On Slide",
      category: "Slip-Ons & Open Flats",
      image: "/company/braided_slide.jpg",
      materials: "Gold Metallic Foiled Synthetic Leather & Natural Tan Weave, Memory Foam Bed",
      features: "Intricate artisan hand-braiding, lightweight flexibility, zero adhesive bleed.",
      productionCapacity: "15,000 pairs / month",
      channel: "Retail Fashion Chains & Online D2C Collections",
    },
    {
      id: "ethnic-embroidered",
      name: "Artisanal Embellished Kolhapuri Slip-On",
      category: "Ethnic & Fusion Daily Wear",
      image: "/company/ethnic_embroidered.jpg",
      materials: "Woven Jacquard Brocade, Terracotta Leather Piping, Hand-Turned Toe Loop",
      features: "Traditional craftsmanship with engineered modern ergonomic footbed.",
      productionCapacity: "10,000 pairs / month",
      channel: "Festive & Premium Ethnic Retail Partners",
    },
  ];

  return (
    <div className="min-h-screen bg-[#FDFBF7] text-[#0F172A] font-sans antialiased selection:bg-[#C27842] selection:text-white pb-16 lg:pb-0">
      {/* ── STICKY EXECUTIVE HEADER ── */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200 shadow-sm transition-all">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 h-16 sm:h-20 flex items-center justify-between">
          {/* Brand & Monogram */}
          <div
            className="flex items-center gap-2.5 sm:gap-3.5 cursor-pointer touch-manipulation"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            data-testid="login-logo"
          >
            <div className="w-9 h-9 sm:w-11 sm:h-11 bg-[#0F172A] text-[#C27842] rounded-lg grid place-items-center font-black text-lg sm:text-xl shadow-ind border border-slate-800 flex-shrink-0">
              SS
            </div>
            <div>
              <div className="font-black tracking-tight text-base sm:text-lg leading-tight text-slate-900 flex items-center gap-1.5">
                <span>SSK FOOTCARE</span>
                <span className="text-[9px] sm:text-[10px] uppercase font-bold tracking-widest px-1 py-0.2 bg-slate-100 text-slate-600 rounded border border-slate-300">
                  LLP
                </span>
              </div>
              <div className="text-[10px] sm:text-[11px] text-slate-500 font-medium tracking-[0.14em] uppercase truncate max-w-[190px] sm:max-w-none">
                Manufacturing & Supply Chain
              </div>
            </div>
          </div>

          {/* Nav Links - Desktop */}
          <nav className="hidden lg:flex items-center gap-6 xl:gap-7 text-xs uppercase font-bold tracking-wider text-slate-600">
            <button
              type="button"
              onClick={() => scrollToSection("what-we-do")}
              className="hover:text-[#C27842] transition-colors"
            >
              Capabilities
            </button>
            <button
              type="button"
              onClick={() => scrollToSection("tech-company")}
              className="hover:text-[#C27842] transition-colors"
            >
              Tech / ERP
            </button>
            <button
              type="button"
              onClick={() => scrollToSection("product-line")}
              className="hover:text-[#C27842] transition-colors"
            >
              Products
            </button>
            <button
              type="button"
              onClick={() => scrollToSection("traction")}
              className="hover:text-[#C27842] transition-colors"
            >
              Clients & Traction
            </button>
            <button
              type="button"
              onClick={() => scrollToSection("leadership")}
              className="hover:text-[#C27842] transition-colors"
            >
              Leadership
            </button>
            <button
              type="button"
              onClick={() => scrollToSection("rfp-inquiry")}
              className="hover:text-[#C27842] transition-colors"
            >
              Inquiry
            </button>
          </nav>

          {/* Action CTAs */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate("/karigar-login")}
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-2 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-300 rounded text-xs font-bold transition-all shadow-sm touch-manipulation"
              data-testid="karigar-portal-btn"
            >
              <HardHat className="w-3.5 h-3.5 text-[#C27842]" />
              <span className="hidden md:inline">Karigar</span> Portal
            </button>

            <button
              type="button"
              onClick={() => setPortalModalOpen(true)}
              className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 bg-[#0F172A] hover:bg-slate-800 text-white rounded text-xs font-bold tracking-wider uppercase transition-all shadow-ind border border-[#0F172A] touch-manipulation"
            >
              <Lock className="w-3.5 h-3.5 text-[#C27842]" />
              <span>Login</span>
            </button>

            {/* Mobile Hamburger Toggle Button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-md border border-slate-300 touch-manipulation flex items-center justify-center"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* ── MOBILE SLIDE-OUT NAVIGATION DRAWER ── */}
        {mobileMenuOpen && (
          <div
            className="lg:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
          >
            <div
              className="absolute right-0 top-0 bottom-0 w-4/5 max-w-sm bg-white shadow-2xl p-6 flex flex-col justify-between overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-200">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-[#0F172A] text-[#C27842] rounded font-black text-sm grid place-items-center">
                      SS
                    </div>
                    <div className="font-black text-sm text-slate-900">SSK FOOTCARE</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setMobileMenuOpen(false)}
                    className="p-1.5 text-slate-500 hover:text-slate-900 rounded-lg hover:bg-slate-100"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="text-[11px] uppercase tracking-widest text-[#C27842] font-bold mb-3">
                  Company Sections
                </div>

                <nav className="space-y-1">
                  <button
                    type="button"
                    onClick={() => scrollToSection("what-we-do")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Capabilities & Operations</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection("tech-company")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Tech / Proprietary ERP</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection("product-line")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Product Showcase</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection("traction")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Clients & Traction</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection("leadership")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Founders & Leadership</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection("rfp-inquiry")}
                    className="w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-slate-800 hover:bg-slate-100 flex items-center justify-between"
                  >
                    <span>Request Proposal / RFQ</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </button>
                </nav>

                <div className="mt-6 pt-5 border-t border-slate-200 space-y-2.5">
                  <button
                    type="button"
                    onClick={() => {
                      setMobileMenuOpen(false);
                      setPortalModalOpen(true);
                    }}
                    className="w-full py-3 bg-[#0F172A] text-white rounded text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 shadow-ind"
                  >
                    <Lock className="w-4 h-4 text-[#C27842]" />
                    <span>Sign In to ERP Console</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setMobileMenuOpen(false);
                      navigate("/karigar-login");
                    }}
                    className="w-full py-3 bg-amber-50 text-amber-900 border border-amber-300 rounded text-xs font-bold flex items-center justify-center gap-2"
                  >
                    <HardHat className="w-4 h-4 text-[#C27842]" />
                    <span>Karigar Worker Login</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => scrollToSection("rfp-inquiry")}
                    className="w-full py-2.5 text-xs text-[#C27842] font-bold text-center hover:underline"
                  >
                    Request B2B Proposal →
                  </button>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-200 text-[11px] text-slate-500 text-center font-mono">
                SSK Footcare Manufacturing LLP
              </div>
            </div>
          </div>
        )}
      </header>

      {/* ── HERO SECTION (SLIDE 1) ── */}
      <section className="relative overflow-hidden bg-gradient-to-b from-white via-[#FAF7F2] to-[#FDFBF7] border-b border-slate-200 pt-8 pb-14 sm:pt-16 sm:pb-20 lg:pt-20 lg:pb-28">
        <div className="absolute inset-0 opacity-25 pointer-events-none bg-[radial-gradient(#C27842_1px,transparent_1px)] [background-size:24px_24px]" />
        <div className="absolute -top-32 -right-32 w-80 sm:w-96 h-80 sm:h-96 bg-amber-200/40 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 -left-20 w-64 sm:w-80 h-64 sm:h-80 bg-orange-100/50 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-12 gap-8 lg:gap-8 items-center">
            {/* Left Content */}
            <div className="lg:col-span-7 space-y-4 sm:space-y-6 text-left">
              <h1 className="text-3xl sm:text-5xl lg:text-6xl font-black text-slate-900 tracking-tight leading-[1.1] break-words">
                Engineering India&apos;s Footwear Supply Chain.
              </h1>

              <p className="text-sm sm:text-base lg:text-lg text-slate-600 leading-relaxed max-w-2xl">
                We design, manufacture, and supply footwear end-to-end — from raw material sourcing through to finished
                packaged product. Serving both high-growth direct-to-consumer online retail and premier B2B contract
                manufacturing brands across India.
              </p>

              {/* Sub-Badges from Slide 1 */}
              <div className="flex flex-wrap items-center gap-2 sm:gap-3 pt-1 sm:pt-2 text-xs font-bold text-slate-700">
                <div className="flex items-center gap-1.5 bg-white border border-slate-300 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-md shadow-sm">
                  <Factory className="w-3.5 h-3.5 text-[#C27842]" />
                  <span>Full In-House Manufacturing</span>
                </div>
                <div className="flex items-center gap-1.5 bg-white border border-slate-300 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-md shadow-sm">
                  <Building2 className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>B2B Contract Manufacturing</span>
                </div>
                <div className="flex items-center gap-1.5 bg-white border border-slate-300 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-md shadow-sm">
                  <ShoppingBag className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Online Retail (Myntra Leader)</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-3 sm:gap-4 pt-2 sm:pt-4">
                <button
                  type="button"
                  onClick={() => scrollToSection("what-we-do")}
                  className="px-6 py-3.5 bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs rounded shadow-ind hover:shadow-ind-lg transition-all flex items-center justify-center gap-2 group touch-manipulation"
                >
                  <span>Explore Capabilities</span>
                  <ArrowRight className="w-4 h-4 text-[#C27842] group-hover:translate-x-1 transition-transform" />
                </button>

                <button
                  type="button"
                  onClick={() => setPortalModalOpen(true)}
                  className="px-6 py-3.5 bg-white text-slate-900 border-2 border-slate-900 font-bold uppercase tracking-wider text-xs rounded hover:bg-slate-50 transition-all flex items-center justify-center gap-2 shadow-sm touch-manipulation"
                >
                  <Lock className="w-4 h-4 text-[#C27842]" />
                  <span>Client & Staff Login</span>
                </button>

                <button
                  type="button"
                  onClick={() => scrollToSection("rfp-inquiry")}
                  className="py-2.5 sm:py-3.5 text-xs uppercase font-bold tracking-wider text-[#C27842] hover:text-[#9b5825] transition-colors flex items-center justify-center gap-1 touch-manipulation"
                >
                  <span>Request B2B Quote</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Right Hero Visual Card */}
            <div className="lg:col-span-5">
              <div className="relative mx-auto max-w-md lg:max-w-none">
                <div className="relative rounded-2xl overflow-hidden border-2 border-slate-900 bg-slate-900 shadow-ind-lg group">
                  <img
                    src="/company/craft_workshop.jpg"
                    alt="SSK Footcare Workshop Line"
                    className="w-full h-64 sm:h-80 lg:h-96 object-cover opacity-85 group-hover:scale-105 transition-transform duration-700"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-[#0F172A] via-[#0F172A]/40 to-transparent" />

                  {/* Floating Metric Badge */}
                  <div className="absolute top-3 left-3 sm:top-4 sm:left-4 bg-white/95 backdrop-blur-sm border border-slate-200 px-3 py-1.5 sm:py-2 rounded-lg shadow-md">
                    <div className="text-[9px] sm:text-[10px] uppercase font-bold tracking-wider text-slate-500">
                      Technology Differentiator
                    </div>
                    <div className="text-xs sm:text-sm font-black text-slate-900 flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-[#C27842]" />
                      Proprietary ERP Engine
                    </div>
                  </div>

                  <div className="absolute bottom-3 left-3 right-3 sm:bottom-4 sm:left-4 sm:right-4 text-white p-3 sm:p-4 bg-black/60 backdrop-blur-md rounded-xl border border-white/10">
                    <div className="flex items-center justify-between text-[11px] sm:text-xs font-mono text-[#C27842] mb-1 font-bold">
                      <span>INTEGRATED WORKSHOP CONSOLE</span>
                      <span className="text-emerald-400">● LIVE</span>
                    </div>
                    <div className="text-sm sm:text-base font-bold leading-snug">
                      From cut to dispatch — one tight, traceable system.
                    </div>
                    <div className="mt-1 sm:mt-2 text-[11px] sm:text-xs text-slate-300 line-clamp-2">
                      Real-time costing, stage-level batch tracking, and zero stage skipping built directly for Indian footwear manufacturing.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── KEY METRICS & TRACTION TICKER ── */}
      <section className="bg-white border-b border-slate-200 py-6 sm:py-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6 lg:gap-8">
            <div className="border-l-4 border-[#C27842] pl-3 sm:pl-4">
              <div className="text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 tracking-tight font-mono">100%</div>
              <div className="text-[11px] sm:text-xs uppercase font-bold tracking-wider text-slate-500 mt-1">In-House Production</div>
              <div className="text-[11px] sm:text-xs text-slate-600 mt-0.5">Sourcing to packing</div>
            </div>

            <div className="border-l-4 border-slate-900 pl-3 sm:pl-4">
              <div className="text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 tracking-tight font-mono">D2C</div>
              <div className="text-[11px] sm:text-xs uppercase font-bold tracking-wider text-slate-500 mt-1">Direct-to-Consumer</div>
              <div className="text-[11px] sm:text-xs text-slate-600 mt-0.5">Marketplace & online retail</div>
            </div>

            <div className="border-l-4 border-emerald-600 pl-3 sm:pl-4">
              <div className="text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 tracking-tight font-mono">4+</div>
              <div className="text-[11px] sm:text-xs uppercase font-bold tracking-wider text-slate-500 mt-1">Enterprise Partners</div>
              <div className="text-[11px] sm:text-xs text-slate-600 mt-0.5">Metro Brands, Siyaram & Myntra</div>
            </div>

            <div className="border-l-4 border-indigo-600 pl-3 sm:pl-4">
              <div className="text-2xl sm:text-3xl lg:text-4xl font-black text-slate-900 tracking-tight font-mono">0</div>
              <div className="text-[11px] sm:text-xs uppercase font-bold tracking-wider text-slate-500 mt-1">Stage Skipping</div>
              <div className="text-[11px] sm:text-xs text-slate-600 mt-0.5">100% Traceable floor</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: WHAT WE DO (SLIDE 2) ── */}
      <section id="what-we-do" className="py-14 sm:py-20 bg-[#FDFBF7] border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10 sm:mb-14">
            <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">
              Product / Service Overview
            </div>
            <h2 className="text-2xl sm:text-4xl font-black text-slate-900 tracking-tight">What We Do</h2>
            <p className="mt-3 sm:mt-4 text-sm sm:text-base text-slate-600 leading-relaxed">
              SSK Footcare Manufacturing LLP designs, manufactures, and supplies footwear end-to-end — from raw material
              sourcing through to finished product — serving both direct-to-consumer and business-to-business channels.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
            {/* Card 1: Raw Material to Finished Product */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind hover:shadow-ind-lg transition-all flex flex-col justify-between">
              <div>
                <div className="w-10 h-10 sm:w-12 sm:h-12 bg-amber-100 text-[#C27842] border border-[#C27842]/30 rounded-lg flex items-center justify-center font-mono font-black text-base sm:text-lg mb-5 sm:mb-6">
                  01
                </div>
                <h3 className="text-lg sm:text-xl font-black text-slate-900 mb-2 sm:mb-3">Raw Material to Finished Product</h3>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Full in-house manufacturing: sourcing, precision leather cutting, upper-making, sole attachment,
                  stringent quality control, and retail-grade packing.
                </p>
              </div>
              <div className="mt-5 sm:mt-6 pt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-mono text-slate-500">
                <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>Zero Outsourcing Compromise</span>
              </div>
            </div>

            {/* Card 2: Direct Online Retail */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind hover:shadow-ind-lg transition-all flex flex-col justify-between">
              <div>
                <div className="w-10 h-10 sm:w-12 sm:h-12 bg-blue-100 text-[#2563EB] border border-[#2563EB]/30 rounded-lg flex items-center justify-center font-mono font-black text-base sm:text-lg mb-5 sm:mb-6">
                  02
                </div>
                <h3 className="text-lg sm:text-xl font-black text-slate-900 mb-2 sm:mb-3">Direct Online Retail</h3>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Own footwear lines designed and sold directly to consumers on India&apos;s leading e-commerce
                  marketplaces, prominently led by Myntra and Flipkart with full retail margins.
                </p>
              </div>
              <div className="mt-5 sm:mt-6 pt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-mono text-slate-500">
                <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>Direct-to-Consumer (D2C) Focus</span>
              </div>
            </div>

            {/* Card 3: B2B Contract Manufacturing */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind hover:shadow-ind-lg transition-all flex flex-col justify-between sm:col-span-2 lg:col-span-1">
              <div>
                <div className="w-10 h-10 sm:w-12 sm:h-12 bg-emerald-100 text-emerald-700 border border-emerald-500/30 rounded-lg flex items-center justify-center font-mono font-black text-base sm:text-lg mb-5 sm:mb-6">
                  03
                </div>
                <h3 className="text-lg sm:text-xl font-black text-slate-900 mb-2 sm:mb-3">B2B Contract Manufacturing</h3>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Private-label and high-volume contract production for established retail and digital fashion brands,
                  including Zecode and SHEIN, backed by guaranteed lead times.
                </p>
              </div>
              <div className="mt-5 sm:mt-6 pt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-mono text-slate-500">
                <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>Enterprise B2B Manufacturing</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: TECH INNOVATION & USP (SLIDE 3) ── */}
      <section id="tech-company" className="py-14 sm:py-20 bg-[#0F172A] text-white border-b border-slate-800 relative overflow-hidden">
        <div className="absolute top-1/2 left-1/4 w-96 h-96 bg-[#C27842]/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-10 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-12 sm:mb-16">
            <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-[#C27842]" />
              <span>Innovation & USP</span>
            </div>
            <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white leading-tight">
              A Manufacturer Built Like a Tech Company
            </h2>
            <p className="mt-3 sm:mt-4 text-sm sm:text-base lg:text-lg text-slate-300 leading-relaxed">
              Our core differentiator is a proprietary, in-house ERP system purpose-built for footwear manufacturing —
              not a generic factory management tool bought off the shelf.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-5 sm:gap-8">
            {/* USP 1 */}
            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 sm:p-8 hover:border-[#C27842] transition-colors relative group">
              <div className="flex items-start gap-3.5 sm:gap-4">
                <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-[#C27842]/20 border border-[#C27842]/50 text-[#C27842] font-mono font-bold grid place-items-center flex-shrink-0 text-sm sm:text-base">
                  1
                </div>
                <div>
                  <h3 className="text-lg sm:text-xl font-bold text-white mb-2 flex items-center gap-2">
                    <span>Real-Time Cost Engineering</span>
                    <TrendingUp className="w-4 h-4 text-[#C27842] opacity-0 group-hover:opacity-100 transition-opacity hidden sm:inline" />
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Every style&apos;s Bill of Materials (BOM), labor operations, and component costs are tracked and
                    calculated automatically, giving accurate PO-level margins instead of estimates.
                  </p>
                </div>
              </div>
            </div>

            {/* USP 2 */}
            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 sm:p-8 hover:border-[#C27842] transition-colors relative group">
              <div className="flex items-start gap-3.5 sm:gap-4">
                <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-blue-500/20 border border-blue-500/50 text-blue-400 font-mono font-bold grid place-items-center flex-shrink-0 text-sm sm:text-base">
                  2
                </div>
                <div>
                  <h3 className="text-lg sm:text-xl font-bold text-white mb-2 flex items-center gap-2">
                    <span>Stage-Level Production Tracking</span>
                    <Layers className="w-4 h-4 text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity hidden sm:inline" />
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Each pair is tracked through every production stage — cutting, upper-making, sole attachment, QC,
                    dispatch — with zero stage skipping, improving on-time delivery and end-to-end traceability.
                  </p>
                </div>
              </div>
            </div>

            {/* USP 3 */}
            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 sm:p-8 hover:border-[#C27842] transition-colors relative group">
              <div className="flex items-start gap-3.5 sm:gap-4">
                <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-emerald-500/20 border border-emerald-500/50 text-emerald-400 font-mono font-bold grid place-items-center flex-shrink-0 text-sm sm:text-base">
                  3
                </div>
                <div>
                  <h3 className="text-lg sm:text-xl font-bold text-white mb-2 flex items-center gap-2">
                    <span>Data-Driven Trend Forecasting</span>
                    <BarChart3 className="w-4 h-4 text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity hidden sm:inline" />
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Historical sales data across our own online and B2B channels feeds a forecasting layer that guides
                    raw material buying and production scheduling, mitigating dead inventory risk.
                  </p>
                </div>
              </div>
            </div>

            {/* USP 4 */}
            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 sm:p-8 hover:border-[#C27842] transition-colors relative group">
              <div className="flex items-start gap-3.5 sm:gap-4">
                <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-amber-500/20 border border-amber-500/50 text-amber-400 font-mono font-bold grid place-items-center flex-shrink-0 text-sm sm:text-base">
                  4
                </div>
                <div>
                  <h3 className="text-lg sm:text-xl font-bold text-white mb-2 flex items-center gap-2">
                    <span>Dual-Channel Reconciliation</span>
                    <RefreshCw className="w-4 h-4 text-amber-400 opacity-0 group-hover:opacity-100 transition-opacity hidden sm:inline" />
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    Purpose-built bank and marketplace reconciliation (including automated Myntra settlements) keeps
                    finance, production, and sales data in total synchronization within one central system.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: PRODUCT VISUALS & MANUFACTURING LINE (SLIDE 4) ── */}
      <section id="product-line" className="py-14 sm:py-20 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 sm:mb-14 gap-4 sm:gap-6">
            <div>
              <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">
                Product Visuals
              </div>
              <h2 className="text-2xl sm:text-4xl font-black text-slate-900 tracking-tight">
                From Our Manufacturing Line
              </h2>
              <p className="mt-2 sm:mt-3 text-sm sm:text-base text-slate-600 max-w-2xl">
                Flat sandals and slip-ons across genuine and synthetic leather, featuring laser-cut patterns,
                hand-braided straps, embellished and printed uppers — manufactured for both our own online listings and
                B2B private-label orders.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-slate-500">Live Catalogue Ready</span>
            </div>
          </div>

          {/* Product Cards Showcase */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
            {productList.map((product) => (
              <div
                key={product.id}
                className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl overflow-hidden shadow-ind hover:shadow-ind-lg transition-all group flex flex-col cursor-pointer touch-manipulation active:scale-[0.99]"
                onClick={() => setSelectedProduct(product)}
              >
                <div className="relative aspect-[4/3] bg-white overflow-hidden border-b-2 border-slate-200">
                  <img
                    src={product.image}
                    alt={product.name}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <div className="absolute top-2.5 left-2.5 sm:top-3 sm:left-3 bg-[#0F172A] text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 sm:px-2.5 sm:py-1 rounded">
                    {product.category}
                  </div>
                  {/* Inspection Trigger on Desktop & Tablet */}
                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity hidden sm:flex items-center justify-center">
                    <span className="bg-white text-slate-900 text-xs font-bold px-3 py-1.5 rounded shadow-lg flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-[#C27842]" />
                      Inspect Spec Sheet
                    </span>
                  </div>
                </div>

                <div className="p-5 sm:p-6 flex-1 flex flex-col justify-between">
                  <div>
                    <h3 className="text-base sm:text-lg font-black text-slate-900 leading-snug group-hover:text-[#C27842] transition-colors">
                      {product.name}
                    </h3>
                    <p className="mt-2 text-xs text-slate-600 line-clamp-2 leading-relaxed">{product.features}</p>
                  </div>

                  <div className="mt-5 pt-4 border-t border-slate-200 space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-600 font-mono">
                      <span>Capacity:</span>
                      <span className="font-bold text-slate-900">{product.productionCapacity}</span>
                    </div>
                    <div className="text-[11px] text-[#C27842] font-semibold">{product.channel}</div>

                    {/* Touch-Friendly Mobile Spec Sheet Button */}
                    <div className="pt-1 sm:hidden">
                      <span className="w-full py-2 bg-slate-900 text-white text-[11px] font-bold uppercase tracking-wider rounded flex items-center justify-center gap-1">
                        <Sparkles className="w-3 h-3 text-[#C27842]" /> View Specifications →
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Modal for Product Spec Inspection */}
          {selectedProduct && (
            <div
              className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4"
              onClick={() => setSelectedProduct(null)}
            >
              <div
                className="bg-white max-w-2xl w-full border-2 border-slate-900 shadow-ind-lg rounded-xl overflow-hidden max-h-[90vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="p-3.5 sm:p-4 bg-slate-900 text-white flex items-center justify-between shrink-0">
                  <div className="font-bold text-xs sm:text-sm tracking-wide flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4 text-[#C27842]" />
                    <span>SSK Product Specification Sheet</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedProduct(null)}
                    className="p-1 text-slate-400 hover:text-white"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="p-4 sm:p-8 space-y-5 sm:space-y-6 overflow-y-auto">
                  <div className="aspect-[16/10] sm:aspect-[16/9] rounded-lg overflow-hidden border border-slate-300">
                    <img
                      src={selectedProduct.image}
                      alt={selectedProduct.name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div>
                    <h4 className="text-xl sm:text-2xl font-black text-slate-900 leading-tight">
                      {selectedProduct.name}
                    </h4>
                    <p className="text-[11px] sm:text-xs uppercase tracking-wider text-slate-500 font-bold mt-1">
                      {selectedProduct.category}
                    </p>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-3 sm:gap-4 text-xs bg-slate-50 p-3.5 sm:p-4 border border-slate-200 rounded-lg">
                    <div>
                      <span className="text-slate-500 font-bold block uppercase tracking-wider">Materials Used</span>
                      <span className="text-slate-800 font-medium">{selectedProduct.materials}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block uppercase tracking-wider">
                        Production Features
                      </span>
                      <span className="text-slate-800 font-medium">{selectedProduct.features}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block uppercase tracking-wider">Monthly Run Rate</span>
                      <span className="text-slate-800 font-mono font-bold">{selectedProduct.productionCapacity}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block uppercase tracking-wider">Channel Fit</span>
                      <span className="text-slate-800 font-semibold">{selectedProduct.channel}</span>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row justify-end gap-2.5 sm:gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setSelectedProduct(null)}
                      className="w-full sm:w-auto px-5 py-2.5 border-2 border-slate-300 text-slate-700 text-xs font-bold uppercase tracking-wider rounded order-2 sm:order-1"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedProduct(null);
                        scrollToSection("rfp-inquiry");
                      }}
                      className="w-full sm:w-auto px-5 py-2.5 bg-[#0F172A] text-white text-xs font-bold uppercase tracking-wider rounded shadow-ind hover:shadow-ind-lg order-1 sm:order-2"
                    >
                      Request Batch Quotation
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── SECTION: REVENUE MODEL (SLIDE 7) ── */}
      <section id="revenue-model" className="py-14 sm:py-20 bg-[#FAF7F2] border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10 sm:mb-14">
            <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">Commercial Architecture</div>
            <h2 className="text-2xl sm:text-4xl font-black text-slate-900 tracking-tight">Revenue Model</h2>
            <p className="mt-3 sm:mt-4 text-sm sm:text-base text-slate-600 leading-relaxed">
              We manufacture footwear from raw material and monetize through two integrated, mutually reinforcing
              channels:
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6 sm:gap-8">
            {/* Channel 1 */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3 sm:mb-4">
                  <span className="text-xs uppercase tracking-widest font-bold text-slate-500">Channel 01</span>
                  <span className="text-xs uppercase font-bold tracking-wider px-2.5 py-1 rounded bg-amber-100 text-[#C27842] font-mono">D2C Channel</span>
                </div>
                <h3 className="text-xl sm:text-2xl font-black text-slate-900 mb-2">Direct-to-Consumer Online Retail</h3>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Own-brand footwear manufactured and sold directly on leading online marketplaces, led by Myntra —
                  capturing the full retail margin on every unit sold without middleman markups.
                </p>
              </div>
              <div className="mt-6 sm:mt-8 bg-amber-50 border border-amber-200 p-3.5 sm:p-4 rounded-lg flex items-center justify-between text-xs font-medium text-amber-900">
                <span>Market Settlement via ERP</span>
                <span className="font-bold">Full Retail Margin</span>
              </div>
            </div>

            {/* Channel 2 */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3 sm:mb-4">
                  <span className="text-xs uppercase tracking-widest font-bold text-slate-500">Channel 02</span>
                  <span className="text-xs uppercase font-bold tracking-wider px-2.5 py-1 rounded bg-emerald-100 text-emerald-700 font-mono">B2B Channel</span>
                </div>
                <h3 className="text-xl sm:text-2xl font-black text-slate-900 mb-2">B2B Contract Manufacturing</h3>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Private-label production for retail and fashion brands such as Zecode and SHEIN, along with wholesale
                  supply to garment/footwear businesses — generating dependable recurring revenue from bulk purchase
                  orders.
                </p>
              </div>
              <div className="mt-6 sm:mt-8 bg-emerald-50 border border-emerald-200 p-3.5 sm:p-4 rounded-lg flex items-center justify-between text-xs font-medium text-emerald-900">
                <span>Enterprise PO Margins</span>
                <span className="font-bold">High Volume Bulk</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: TRACTION & CLIENT PORTFOLIO (SLIDE 9) ── */}
      <section id="traction" className="py-14 sm:py-20 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10 sm:mb-14">
            <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">Traction</div>
            <h2 className="text-2xl sm:text-4xl font-black text-slate-900 tracking-tight">Who We Work With</h2>
            <p className="mt-3 sm:mt-4 text-sm sm:text-base text-slate-600 leading-relaxed">
              SSK Footcare supplies four established business customers across marketplace and B2B channels, alongside
              direct consumer sales on Myntra and Flipkart.
            </p>
          </div>

          {/* Client Logos / Monogram Cards from Slide 9 */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-6">
            {/* Myntra */}
            <div className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl p-4 sm:p-6 text-center shadow-ind hover:border-[#C27842] transition-colors flex flex-col items-center justify-center">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-red-600 text-white font-black text-lg sm:text-xl flex items-center justify-center mb-3 sm:mb-4 shadow-sm">
                M
              </div>
              <div className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">Myntra Designs Pvt Ltd</div>
              <div className="text-[10px] sm:text-[11px] uppercase tracking-wider text-slate-500 mt-1 font-semibold">
                Online Marketplace
              </div>
            </div>

            {/* Nexgen */}
            <div className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl p-4 sm:p-6 text-center shadow-ind hover:border-[#C27842] transition-colors flex flex-col items-center justify-center">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-blue-700 text-white font-black text-lg sm:text-xl flex items-center justify-center mb-3 sm:mb-4 shadow-sm">
                N
              </div>
              <div className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">Nexgen Fashion Pvt Ltd</div>
              <div className="text-[10px] sm:text-[11px] uppercase tracking-wider text-slate-500 mt-1 font-semibold">
                B2B / Wholesale
              </div>
            </div>

            {/* Siyaram */}
            <div className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl p-4 sm:p-6 text-center shadow-ind hover:border-[#C27842] transition-colors flex flex-col items-center justify-center">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-emerald-700 text-white font-black text-lg sm:text-xl flex items-center justify-center mb-3 sm:mb-4 shadow-sm">
                S
              </div>
              <div className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">Siyaram Silk Mills</div>
              <div className="text-[10px] sm:text-[11px] uppercase tracking-wider text-slate-500 mt-1 font-semibold">
                B2B / Vendor Partner
              </div>
            </div>

            {/* Metro Brands */}
            <div className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl p-4 sm:p-6 text-center shadow-ind hover:border-[#C27842] transition-colors flex flex-col items-center justify-center">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-purple-700 text-white font-black text-lg sm:text-xl flex items-center justify-center mb-3 sm:mb-4 shadow-sm">
                M
              </div>
              <div className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">Metro Brands Ltd</div>
              <div className="text-[10px] sm:text-[11px] uppercase tracking-wider text-slate-500 mt-1 font-semibold">
                B2B / Contract Mfg.
              </div>
            </div>

            {/* Flipkart */}
            <div className="bg-[#FAF8F5] border-2 border-slate-300 rounded-xl p-4 sm:p-6 text-center shadow-ind hover:border-[#C27842] transition-colors flex flex-col items-center justify-center col-span-2 sm:col-span-1">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-amber-500 text-white font-black text-lg sm:text-xl flex items-center justify-center mb-3 sm:mb-4 shadow-sm">
                F
              </div>
              <div className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">Flipkart Pvt Ltd</div>
              <div className="text-[10px] sm:text-[11px] uppercase tracking-wider text-slate-500 mt-1 font-semibold">
                Online Marketplace
              </div>
            </div>
          </div>

          {/* Bottom Highlight banner from Slide 9 */}
          <div className="mt-8 sm:mt-10 bg-slate-900 text-white rounded-xl p-5 sm:p-8 flex flex-col sm:flex-row items-center gap-4 sm:gap-6 shadow-ind text-center sm:text-left">
            <div className="text-3xl sm:text-5xl font-black text-[#C27842] font-mono shrink-0">4+</div>
            <div className="text-xs sm:text-base text-slate-200 leading-relaxed">
              Active paying B2B customers, plus direct consumer sales on Myntra and Flipkart — spanning marketplace
              retail, contract manufacturing, and raw-material supply relationships.
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: LEADERSHIP & OWNERSHIP (SLIDES 5 & 6) ── */}
      <section id="leadership" className="py-14 sm:py-20 bg-[#FAF7F2] border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10 sm:mb-14">
            <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">
              Founder & Team Details
            </div>
            <h2 className="text-2xl sm:text-4xl font-black text-slate-900 tracking-tight">Leadership</h2>
            <p className="mt-3 sm:mt-4 text-sm sm:text-base text-slate-600 leading-relaxed">
              Blending generational footwear craftsmanship with modern computer science engineering and institutional
              financial management.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6 sm:gap-8">
            {/* Umesh Suwasiya */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-3.5 sm:gap-4 mb-5 sm:mb-6">
                  <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-[#0F172A] text-[#C27842] border-2 border-[#C27842] font-black text-xl sm:text-2xl flex items-center justify-center font-mono shadow-sm shrink-0">
                    US
                  </div>
                  <div>
                    <h3 className="text-xl sm:text-2xl font-black text-slate-900">Umesh Suwasiya</h3>
                    <div className="text-[11px] sm:text-xs font-bold text-[#C27842] tracking-wider uppercase">
                      Co-Founder & Director — Product & Front-of-Business
                    </div>
                    <div className="text-xs text-slate-500 font-mono mt-0.5 font-semibold">B.E., Computer Science</div>
                  </div>
                </div>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Took over and scaled his family&apos;s existing footwear manufacturing business, which has long
                  supplied Indian retail majors including Metro Brands and Reliance Retail — giving SSK Footcare deep,
                  first-hand relationships and credibility in the domestic market. Leads product development, design,
                  order management, and India-facing business operations, and drove the build of the company&apos;s
                  proprietary ERP system.
                </p>
              </div>
              <div className="mt-5 sm:mt-6 pt-4 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-500">
                <span>Co-Founder</span>
                <span className="font-semibold text-slate-900">Indian National</span>
              </div>
            </div>

            {/* Naresh Kurdiya */}
            <div className="bg-white border-2 border-slate-300 rounded-xl p-6 sm:p-8 shadow-ind flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-3.5 sm:gap-4 mb-5 sm:mb-6">
                  <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-[#0F172A] text-emerald-400 border-2 border-emerald-500 font-black text-xl sm:text-2xl flex items-center justify-center font-mono shadow-sm shrink-0">
                    NK
                  </div>
                  <div>
                    <h3 className="text-xl sm:text-2xl font-black text-slate-900">Naresh Kurdiya</h3>
                    <div className="text-[11px] sm:text-xs font-bold text-emerald-700 tracking-wider uppercase">
                      Co-Founder & Director — Production, QC & HR
                    </div>
                    <div className="text-xs text-slate-500 font-mono mt-0.5 font-semibold">B.Com, IPCC (Accounts)</div>
                  </div>
                </div>
                <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                  Brings prior hands-on experience working alongside his father in the export of footwear to European
                  countries, with a strong grounding in accounts and export operations. Leads production management,
                  quality control, and human resource management for SSK Footcare across the floor.
                </p>
              </div>
              <div className="mt-5 sm:mt-6 pt-4 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-500">
                <span>Co-Founder</span>
                <span className="font-semibold text-slate-900">Indian National</span>
              </div>
            </div>
          </div>

          {/* Company Structure */}
          <div className="mt-6 sm:mt-8 bg-white border-2 border-slate-300 rounded-xl p-4 sm:p-6 shadow-ind">
            <div className="text-xs uppercase font-bold tracking-wider text-slate-500 mb-1">
              Company Structure & Ownership
            </div>
            <div className="text-xs sm:text-sm font-semibold text-slate-800">
              Structure: Limited Liability Partnership (LLP), jointly owned and managed by founding partners since inception — no external shareholders.
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION: B2B INQUIRY / RFQ TOUCHPOINT ── */}
      <section id="rfp-inquiry" className="py-14 sm:py-20 bg-[#FDFBF7] border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white border-2 border-slate-300 rounded-2xl p-5 sm:p-8 md:p-12 shadow-ind">
            <div className="text-center max-w-xl mx-auto mb-8 sm:mb-10">
              <div className="text-xs uppercase font-bold tracking-[0.25em] text-[#C27842] mb-2">Partner With Us</div>
              <h2 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">Request a Manufacturing Proposal</h2>
              <p className="mt-2 text-xs sm:text-sm text-slate-600">
                Direct wholesale quotes, private-label design sampling, or contract production inquiries.
              </p>
            </div>

            {inquirySuccess ? (
              <div className="bg-emerald-50 border-2 border-emerald-300 p-6 sm:p-8 text-center rounded-xl space-y-3">
                <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 mx-auto grid place-items-center">
                  <Check className="w-6 h-6" />
                </div>
                <h4 className="text-lg sm:text-xl font-black text-emerald-900">Thank you for your inquiry!</h4>
                <p className="text-xs sm:text-sm text-emerald-800 max-w-md mx-auto">
                  Our directors Umesh Suwasiya and Naresh Kurdiya will review your specs and contact you within 24
                  business hours.
                </p>
                <button
                  type="button"
                  onClick={() => setInquirySuccess(false)}
                  className="mt-4 px-5 py-2.5 bg-emerald-700 text-white text-xs font-bold uppercase tracking-wider rounded"
                >
                  Send Another Inquiry
                </button>
              </div>
            ) : (
              <form onSubmit={handleInquirySubmit} className="space-y-4 sm:space-y-5">
                <div className="grid sm:grid-cols-2 gap-4 sm:gap-5">
                  <div>
                    <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                      Your Full Name
                    </label>
                    <input
                      type="text"
                      required
                      value={inquiryName}
                      onChange={(e) => setInquiryName(e.target.value)}
                      placeholder="e.g. Rahul Sharma"
                      className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                      Company / Brand Name
                    </label>
                    <input
                      type="text"
                      required
                      value={inquiryCompany}
                      onChange={(e) => setInquiryCompany(e.target.value)}
                      placeholder="e.g. Metro Brands / Retail Label"
                      className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid sm:grid-cols-2 gap-4 sm:gap-5">
                  <div>
                    <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                      Work Email
                    </label>
                    <input
                      type="email"
                      required
                      value={inquiryEmail}
                      onChange={(e) => setInquiryEmail(e.target.value)}
                      placeholder="rahul@brand.com"
                      className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                      Partnership Type
                    </label>
                    <select
                      value={inquiryType}
                      onChange={(e) => setInquiryType(e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="Private Label / Contract Mfg">Private Label / Contract Mfg</option>
                      <option value="Bulk Wholesale Footwear Orders">Bulk Wholesale Footwear Orders</option>
                      <option value="E-Commerce Marketplace Supply">E-Commerce Marketplace Supply</option>
                      <option value="Raw Material / Component Vendor">Raw Material / Component Vendor</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                    Estimated Production Volume
                  </label>
                  <select
                    value={inquiryVolume}
                    onChange={(e) => setInquiryVolume(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                  >
                    <option value="500 - 1,000 pairs/month">500 - 1,000 pairs/month (Trial Batch)</option>
                    <option value="1,000 - 5,000 pairs/month">1,000 - 5,000 pairs/month</option>
                    <option value="5,000 - 20,000 pairs/month">5,000 - 20,000 pairs/month (Full Line)</option>
                    <option value="20,000+ pairs/month">20,000+ pairs/month (Enterprise)</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                    Requirements & Specs
                  </label>
                  <textarea
                    rows={3}
                    value={inquiryMessage}
                    onChange={(e) => setInquiryMessage(e.target.value)}
                    placeholder="Tell us about your target styles (laser-cut sandals, braids, slip-ons), timeline, and quality requirements..."
                    className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm text-slate-900 focus:border-[#2563EB] focus:outline-none"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full sm:w-auto px-8 py-3.5 bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg transition-all flex items-center justify-center gap-2 touch-manipulation min-h-[48px]"
                >
                  <Send className="w-3.5 h-3.5 text-[#C27842]" />
                  <span>Submit Client Request</span>
                </button>
              </form>
            )}
          </div>
        </div>
      </section>

      {/* ── FOOTER & THANK YOU (SLIDE 11) ── */}
      <footer className="bg-[#0F172A] text-slate-400 py-12 sm:py-16 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-12 gap-8 sm:gap-10 pb-10 sm:pb-12 border-b border-slate-800">
            {/* Column 1: Monogram & Identity */}
            <div className="md:col-span-5 space-y-3 sm:space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 sm:w-10 sm:h-10 bg-slate-900 text-[#C27842] border border-[#C27842] rounded-lg grid place-items-center font-black text-lg sm:text-xl">
                  SS
                </div>
                <div>
                  <div className="font-black text-base sm:text-lg text-white tracking-tight">
                    SSK FOOTCARE MANUFACTURING LLP
                  </div>
                  <div className="text-[11px] sm:text-xs text-slate-400 uppercase tracking-wider">
                    Engineering India&apos;s Footwear Supply Chain
                  </div>
                </div>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
                Proprietary manufacturing technology combined with generation-proven footwear craftsmanship.
                Leading direct online retail and enterprise B2B contract manufacturing.
              </p>
              <div className="text-xs font-mono text-[#C27842] font-semibold break-all">
                ssk-footcare-manufacturing-erp.vercel.app
              </div>
            </div>

            {/* Column 2: Leadership Contact */}
            <div className="md:col-span-4 space-y-3">
              <div className="text-xs font-bold uppercase tracking-widest text-white">Founding Partners</div>
              <div className="space-y-2 text-xs">
                <div>
                  <div className="text-white font-bold">Umesh Suwasiya</div>
                  <div className="text-slate-400">Co-Founder & Director — Product, Design & Front-of-Business</div>
                </div>
                <div>
                  <div className="text-white font-bold">Naresh Kurdiya</div>
                  <div className="text-slate-400">Co-Founder & Director — Production, QC & HR</div>
                </div>
              </div>
            </div>

            {/* Column 3: Portals & Quick Links */}
            <div className="md:col-span-3 space-y-3">
              <div className="text-xs font-bold uppercase tracking-widest text-white">Direct Portals</div>
              <ul className="space-y-2 text-xs">
                <li>
                  <button
                    type="button"
                    onClick={() => setPortalModalOpen(true)}
                    className="hover:text-white transition-colors flex items-center gap-1.5 touch-manipulation"
                  >
                    <Lock className="w-3.5 h-3.5 text-[#C27842]" /> Staff & Floor Console Login
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => navigate("/karigar-login")}
                    className="hover:text-white transition-colors flex items-center gap-1.5 touch-manipulation"
                  >
                    <HardHat className="w-3.5 h-3.5 text-[#C27842]" /> Karigar (Worker) Phone Login
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => {
                      setForgotOpen(true);
                      setForgotResult(null);
                    }}
                    className="hover:text-white transition-colors touch-manipulation"
                  >
                    Reset Lost Password
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div className="pt-6 sm:pt-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-3 text-center sm:text-left">
            <div>© {new Date().getFullYear()} SSK Footcare Manufacturing LLP. All rights reserved.</div>
            <div className="font-mono text-[11px]">Limited Liability Partnership (LLP) • Startup India</div>
          </div>
        </div>
      </footer>

      {/* ── MOBILE STICKY FLOATING QUICK ACTION BAR (PHONES ONLY) ── */}
      <aside aria-label="Mobile quick actions" className="lg:hidden fixed bottom-0 left-0 right-0 z-30 bg-[#0F172A]/95 backdrop-blur-md border-t border-slate-800 px-3 py-2.5 flex items-center justify-between gap-2 shadow-2xl">
        <button
          type="button"
          onClick={() => setPortalModalOpen(true)}
          className="flex-1 py-2.5 bg-[#C27842] hover:bg-[#a65d24] text-white text-xs font-bold rounded flex items-center justify-center gap-1.5 shadow touch-manipulation"
        >
          <Lock className="w-3.5 h-3.5" />
          <span>Console Sign In</span>
        </button>

        <button
          type="button"
          onClick={() => navigate("/karigar-login")}
          className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-400/30 text-xs font-bold rounded flex items-center justify-center gap-1.5 touch-manipulation"
        >
          <HardHat className="w-3.5 h-3.5 text-[#C27842]" />
          <span>Karigar Portal</span>
        </button>

        <button
          type="button"
          onClick={() => scrollToSection("rfp-inquiry")}
          className="px-3 py-2.5 bg-slate-800 text-slate-200 border border-slate-700 text-xs font-bold rounded flex items-center justify-center touch-manipulation"
          title="Request Proposal"
        >
          <Send className="w-3.5 h-3.5 text-[#C27842]" />
        </button>
      </aside>

      {/* ── MODAL: PORTAL SIGN IN (TRIGGERABLE ANYWHERE) ── */}
      {portalModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4"
          onClick={() => setPortalModalOpen(false)}
        >
          <div
            className="bg-white max-w-md w-full border-2 border-slate-900 shadow-ind-lg rounded-xl overflow-hidden max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 sm:px-6 py-3.5 sm:py-4 bg-[#0F172A] text-white flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 bg-[#C27842] text-white rounded font-black text-xs grid place-items-center">
                  SS
                </div>
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#C27842]">SSK Footcare</div>
                  <div className="text-xs sm:text-sm font-bold">Sign In to Operations Console</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPortalModalOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={onSubmit} className="p-5 sm:p-6 space-y-4 overflow-y-auto">
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                  Email
                </label>
                <input
                  data-testid="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@sskfootcare.com"
                  required
                  className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm font-mono text-slate-900 focus:border-[#2563EB] focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-700 block mb-1">
                  Password
                </label>
                <input
                  data-testid="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-base sm:text-sm font-mono text-slate-900 focus:border-[#2563EB] focus:outline-none"
                />
              </div>

              {error && (
                <div data-testid="login-error" className="text-xs text-red-700 bg-red-50 border border-red-200 px-3 py-2 font-medium">
                  {error}
                </div>
              )}

              <button
                data-testid="login-submit"
                disabled={busy}
                type="submit"
                className="w-full bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs py-3.5 border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg transition-all flex items-center justify-center gap-2 touch-manipulation min-h-[44px]"
              >
                {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>Sign In</span>
              </button>

              <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-200">
                <button
                  type="button"
                  data-testid="karigar-login-link"
                  onClick={() => {
                    setPortalModalOpen(false);
                    navigate("/karigar-login");
                  }}
                  className="font-bold text-[#C27842] hover:underline flex items-center gap-1 touch-manipulation p-1"
                >
                  <HardHat className="w-3.5 h-3.5" />
                  Karigar Phone Login
                </button>
                <button
                  type="button"
                  data-testid="forgot-password-link"
                  onClick={() => {
                    setPortalModalOpen(false);
                    setForgotOpen(true);
                    setForgotEmail(email);
                    setForgotResult(null);
                  }}
                  className="text-[#2563EB] hover:underline font-bold uppercase tracking-wider text-[11px] touch-manipulation p-1"
                >
                  Forgot Password?
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: FORGOT PASSWORD ── */}
      {forgotOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-3 sm:p-4 backdrop-blur-sm"
          onClick={() => setForgotOpen(false)}
          data-testid="forgot-password-modal"
        >
          <div
            className="bg-white w-full max-w-md border-2 border-[#0F172A] shadow-ind-lg rounded-xl overflow-hidden max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 sm:px-6 py-3.5 sm:py-4 bg-slate-900 text-white border-b border-slate-800 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold">
                  Password Recovery
                </div>
                <h3 className="text-base sm:text-lg font-black">Forgot your password?</h3>
              </div>
              <button
                type="button"
                onClick={() => setForgotOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={submitForgot} className="p-5 sm:p-6 space-y-4 overflow-y-auto">
              <p className="text-xs text-slate-600">
                Enter your account email — we&apos;ll issue a single-use password reset link that expires in 1 hour.
              </p>
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-600 block mb-1">Email</label>
                <input
                  data-testid="forgot-email-input"
                  type="email"
                  required
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  className="w-full border-2 border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-base sm:text-sm"
                />
              </div>

              {forgotResult && (
                <div
                  className="text-xs bg-slate-50 border-2 border-slate-300 p-3 space-y-1.5"
                  data-testid="forgot-result"
                >
                  <div className="font-semibold text-slate-800">{forgotResult.message}</div>
                  {forgotResult.email_status === "email_not_configured" && forgotResult.dev_reset_url && (
                    <div className="text-xs text-amber-900 bg-amber-50 border border-amber-300 p-2 rounded">
                      <strong>Email service is in dev mode</strong> — reset link:
                      <div className="mt-1 break-all font-mono text-[11px] text-slate-800 bg-white border border-slate-300 p-1.5">
                        <a href={forgotResult.dev_reset_url} target="_blank" rel="noreferrer" className="underline">
                          {forgotResult.dev_reset_url}
                        </a>
                      </div>
                    </div>
                  )}
                  {forgotResult.email_status && forgotResult.email_status !== "email_not_configured" && (
                    <div className="text-xs text-red-800 font-semibold">
                      Email delivery failed ({forgotResult.email_status}). Please contact your system administrator.
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setForgotOpen(false)}
                  className="flex-1 border-2 border-slate-300 text-slate-700 font-bold uppercase tracking-wider text-xs py-3 hover:border-slate-500 touch-manipulation"
                >
                  Close
                </button>
                <button
                  type="submit"
                  data-testid="forgot-submit"
                  disabled={forgotBusy}
                  className="flex-1 bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs py-3 border-2 border-[#0F172A] hover:shadow-ind disabled:opacity-50 flex items-center justify-center gap-2 touch-manipulation"
                >
                  {forgotBusy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Send reset link
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
