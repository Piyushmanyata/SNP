import React, { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Loader2, X, AlertTriangle, RefreshCw } from "lucide-react";

export function Button({ variant = "primary", size = "md", className = "", children, ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed";
  const sizes = {
    sm: "min-h-[44px] min-w-[44px] px-3 text-sm",
    md: "min-h-[44px] px-5 text-sm",
    lg: "min-h-[52px] px-6 text-base",
  };
  const variants = {
    primary: "bg-emerald-700 text-white hover:bg-emerald-800",
    secondary: "bg-slate-900 text-white hover:bg-slate-800",
    outline: "bg-white text-slate-900 border-2 border-slate-800 hover:bg-slate-100 hover:border-emerald-700 hover:text-emerald-800",
    ghost: "bg-transparent text-slate-700 underline underline-offset-4 hover:bg-slate-100",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Card({ className = "", children, ...props }) {
  return (
    <div
      className={`bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5 sm:p-6 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function Field({ label, children, required, hint }) {
  return (
    <label className="block">
      {label && (
        <span className="block text-xs font-mono uppercase tracking-widest text-slate-500 mb-1.5">
          {label} {required && <span className="text-rose-500">*</span>}
        </span>
      )}
      {children}
      {hint && <span className="block text-xs text-slate-600 mt-1">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500";

export const Input = React.forwardRef(function Input({ className = "", ...props }, ref) {
  return <input ref={ref} className={`${inputCls} ${className}`} {...props} />;
});

export function Select({ className = "", children, ...props }) {
  return (
    <select className={`${inputCls} ${className}`} {...props}>
      {children}
    </select>
  );
}

export function Badge({ tone = "slate", children, className = "", ...props }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    emerald: "bg-emerald-100 text-emerald-700",
    amber: "bg-amber-100 text-amber-700",
    indigo: "bg-indigo-100 text-indigo-700",
    rose: "bg-rose-100 text-rose-700",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${tones[tone]} ${className}`} {...props}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  if (status === "seen") return <Badge tone="emerald">Seen</Badge>;
  if (status === "arrived") return <Badge tone="indigo">Arrived</Badge>;
  return <Badge tone="amber">Registered</Badge>;
}

export function Spinner({ className = "" }) {
  return <Loader2 className={`animate-spin ${className}`} />;
}

export function Alert({ tone = "rose", children, className = "" }) {
  const tones = {
    rose: "bg-rose-50 border-rose-200 text-rose-700",
    amber: "bg-amber-50 border-amber-200 text-amber-800",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
  };
  if (!children) return null;
  return (
    <div role="alert" className={`flex items-start gap-2 text-sm border rounded-xl px-3.5 py-2.5 ${tones[tone]} ${className}`}>
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function ErrorCard({ message, onRetry }) {
  return (
    <Card className="border-rose-200">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-rose-500" />
        <div className="flex-1">
          <p className="text-sm text-slate-700">{message || "Something went wrong."}</p>
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} data-testid="error-retry-button">
            <RefreshCw className="w-4 h-4" /> Retry
          </Button>
        )}
      </div>
    </Card>
  );
}

export function Modal({ open, onClose, title, children, size = "md" }) {
  const dialogRef = useRef(null);
  const focusable = 'button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]';
  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (!dialogRef.current.contains(document.activeElement)) {
      (dialogRef.current.querySelector(focusable) || dialogRef.current).focus();
    }
    return () => {
      document.body.style.overflow = prev;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose?.();
      if (e.key !== "Tab") return;
      const elements = [...dialogRef.current.querySelectorAll(focusable)];
      const first = elements[0] || dialogRef.current;
      const last = elements[elements.length - 1] || first;
      if (!elements.length || !dialogRef.current.contains(document.activeElement) || (e.shiftKey ? document.activeElement === first : document.activeElement === last)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  if (!open) return null;
  const widths = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-0 sm:p-4 overflow-y-auto">
      <div role="presentation" className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative my-0 sm:my-8 bg-white w-full ${widths[size]} rounded-t-2xl sm:rounded-2xl shadow-2xl border border-slate-200 max-h-[100vh] sm:max-h-[90vh] overflow-y-auto animate-fade-up`}
      >
        <div className="sticky top-0 bg-white flex items-center justify-between px-5 py-4 border-b border-slate-100 z-10">
          <h3 className="font-display font-bold text-lg text-slate-900">{title}</h3>
          {onClose && <button type="button" onClick={onClose} aria-label="Close dialog" className="min-h-[44px] min-w-[44px] flex items-center justify-center text-slate-500 hover:text-slate-700" data-testid="modal-close-button">
            <X className="w-5 h-5" />
          </button>}
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body
  );
}

export function Stat({ label, value, tone = "slate", testid }) {
  const tones = {
    slate: "text-slate-900",
    emerald: "text-emerald-600",
    amber: "text-amber-600",
  };
  return (
    <Card className="min-w-0 !p-3 sm:!p-5">
      <p className="truncate text-[11px] sm:text-xs font-mono uppercase tracking-normal sm:tracking-widest text-slate-600">{label}</p>
      <p className={`mt-1 sm:mt-2 text-2xl sm:text-3xl font-display font-extrabold tabular-nums ${tones[tone]}`} data-testid={testid}>{value}</p>
    </Card>
  );
}
