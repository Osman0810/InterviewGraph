"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
};

export function Button({ className, variant = "primary", type = "button", ...props }: ButtonProps) {
  const variants = {
    primary: "bg-primary-strong text-white hover:bg-primary focus-visible:ring-primary/40",
    secondary: "border border-app-border bg-surface-elevated text-slate-100 hover:border-slate-500 hover:bg-slate-800",
    ghost: "text-slate-300 hover:bg-slate-800 hover:text-white",
    danger: "bg-rose-500 text-white hover:bg-rose-400",
  };
  return <button type={type} className={cx("inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50", variants[variant], className)} {...props} />;
}

export function Card({ className, children, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cx("rounded-xl border border-app-border bg-surface-elevated shadow-sm shadow-black/20", className)} {...props}>{children}</section>;
}

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "primary" | "success" | "warning" | "danger"; className?: string }) {
  const tones = {
    neutral: "border-app-border bg-slate-800/70 text-slate-300",
    primary: "border-indigo-400/25 bg-indigo-400/10 text-indigo-200",
    success: "border-success/25 bg-success/10 text-green-200",
    warning: "border-amber-400/25 bg-amber-400/10 text-amber-100",
    danger: "border-rose-400/25 bg-rose-400/10 text-rose-200",
  };
  return <span className={cx("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold", tones[tone], className)}>{children}</span>;
}

export function ProgressBar({ value, className, label = "Progress" }: { value: number; className?: string; label?: string }) {
  const boundedValue = Math.max(0, Math.min(100, value));
  return <div className={cx("h-2 overflow-hidden rounded-full bg-slate-800", className)} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(boundedValue)}><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${boundedValue}%` }} /></div>;
}

export function MetricCard({ label, value, detail, className }: { label: string; value: ReactNode; detail?: ReactNode; className?: string }) {
  return <Card className={cx("p-5", className)}><p className="text-xs font-semibold uppercase tracking-[.12em] text-app-muted">{label}</p><p className="mt-3 text-3xl font-bold tracking-tight text-white">{value}</p>{detail ? <p className="mt-2 text-sm text-app-muted">{detail}</p> : null}</Card>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return <div className="flex flex-wrap items-end justify-between gap-5 border-b border-app-border pb-6"><div>{eyebrow ? <p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">{eyebrow}</p> : null}<h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">{title}</h1>{description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-app-muted">{description}</p> : null}</div>{action}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <Card className="p-8 text-center"><h2 className="text-lg font-semibold text-white">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-app-muted">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</Card>;
}

export function ErrorState({ title = "Something went wrong", description, action }: { title?: string; description: string; action?: ReactNode }) {
  return <Card className="border-rose-400/30 p-7" role="alert"><p className="text-xs font-semibold uppercase tracking-[.14em] text-rose-300">Action needed</p><h1 className="mt-3 text-2xl font-bold text-white">{title}</h1><p className="mt-3 text-sm leading-6 text-slate-300">{description}</p>{action ? <div className="mt-6 flex flex-wrap gap-3">{action}</div> : null}</Card>;
}

export function LoadingState({ label = "Loading workspace" }: { label?: string }) {
  return <Card className="flex items-center gap-4 p-6" role="status" aria-live="polite"><div className="size-7 animate-spin rounded-full border-2 border-slate-700 border-t-primary" aria-hidden="true" /><p className="text-sm font-semibold text-slate-200">{label}</p></Card>;
}

export function Sidebar() {
  return <aside className="hidden w-60 shrink-0 border-r border-app-border bg-surface px-4 py-5 lg:flex lg:flex-col"><Link href="/" className="flex items-center gap-3 font-semibold text-white"><span className="grid size-8 place-items-center rounded-lg bg-primary-strong text-xs font-bold">IG</span><span>InterviewGraph</span></Link><nav className="mt-10 space-y-1 text-sm"><Link href="/" aria-current="page" className="flex items-center rounded-lg bg-indigo-400/10 px-3 py-2.5 font-medium text-indigo-100">New analysis</Link><p className="px-3 py-2 text-xs text-app-muted">Your active session stays available as you move through analysis, interview, and results.</p></nav><p className="mt-auto px-3 text-xs leading-5 text-app-muted">Evidence-led interview preparation</p></aside>;
}

export function TopBar({ children, showBrand = false }: { children?: ReactNode; showBrand?: boolean }) {
  return <header className="flex min-h-16 items-center justify-between border-b border-app-border bg-surface/80 px-4 backdrop-blur sm:px-6 lg:px-8"><Link href="/" className={cx("flex items-center gap-2 font-semibold text-white", showBrand ? "" : "lg:hidden")}><span className="grid size-7 place-items-center rounded-md bg-primary-strong text-[10px] font-bold">IG</span>InterviewGraph</Link>{!showBrand ? <div className="hidden text-sm text-app-muted lg:block">Interview workspace</div> : null}<div className="ml-auto">{children}</div></header>;
}

export function AppShell({ children, topBar, showSidebar = true }: { children: ReactNode; topBar?: ReactNode; showSidebar?: boolean }) {
  return <div className="min-h-screen bg-background text-foreground lg:flex">{showSidebar ? <Sidebar /> : null}<div className="min-w-0 flex-1"><TopBar showBrand={!showSidebar}>{topBar}</TopBar><main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">{children}</main></div></div>;
}

type SessionSection = "overview" | "interview" | "gaps" | "plan" | "replay";

export function SessionAppShell({ children, sessionId, provider: initialProvider, active: activeOverride }: { children: ReactNode; sessionId: string; provider?: string; active?: SessionSection }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [provider, setProvider] = useState(initialProvider ?? "");
  const derivedActive = useMemo<SessionSection>(() => {
    if (pathname.includes("/interview")) return "interview";
    if (pathname.includes("/results")) {
      const tab = searchParams.get("tab");
      return tab === "plan" || tab === "replay" ? tab : "gaps";
    }
    return "overview";
  }, [pathname, searchParams]);
  const active = activeOverride ?? derivedActive;
  useEffect(() => {
    let cancelled = false;
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${baseUrl}/sessions/${sessionId}/analysis-summary`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((summary) => { if (!cancelled && !initialProvider) setProvider(summary?.ai_provider ?? ""); })
      .catch(() => { if (!cancelled) setProvider(""); });
    return () => { cancelled = true; };
  }, [initialProvider, sessionId]);
  const items: { id: SessionSection; label: string; href: string }[] = [
    { id: "overview", label: "Overview", href: `/session/${sessionId}/analysis` },
    { id: "interview", label: "Interview", href: `/session/${sessionId}/interview` },
    { id: "gaps", label: "Knowledge Gaps", href: `/session/${sessionId}/results?tab=gaps` },
    { id: "plan", label: "Study Plan", href: `/session/${sessionId}/results?tab=plan` },
    { id: "replay", label: "Replay", href: `/session/${sessionId}/results?tab=replay` },
  ];
  const navigation = (compact = false) => <nav className={cx(compact ? "flex gap-1 overflow-x-auto px-4 py-2" : "space-y-1", "text-sm")} aria-label="Session navigation">{items.map((item) => <Link key={item.id} href={item.href} aria-current={active === item.id ? "page" : undefined} className={cx(compact ? "whitespace-nowrap px-3 py-2" : "flex px-3 py-2.5", "rounded-lg font-medium transition", active === item.id ? "bg-indigo-400/10 text-indigo-100" : "text-slate-400 hover:bg-slate-800 hover:text-slate-100")}>{item.label}</Link>)}</nav>;
  if (activeOverride) return <>{children}</>;
  return <div className="session-app-shell min-h-screen bg-background text-foreground"><header className="flex min-h-16 items-center justify-between border-b border-app-border bg-surface/80 px-4 backdrop-blur sm:px-6"><Link href="/" className="flex items-center gap-2.5 font-semibold text-white"><span className="grid size-7 place-items-center rounded-md bg-primary-strong text-[10px] font-bold">IG</span><span>InterviewGraph</span></Link><div className="flex items-center gap-3">{provider ? <Badge tone="primary" className="font-mono uppercase tracking-wide">{provider}</Badge> : null}<Link href="/" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800 hover:text-white sm:inline-flex">New Analysis</Link></div></header><div className="border-b border-app-border bg-surface lg:hidden">{navigation(true)}</div><div className="lg:flex"><aside className="hidden min-h-[calc(100vh-4rem)] w-56 shrink-0 border-r border-app-border bg-surface px-3 py-5 lg:flex lg:flex-col">{navigation()}<Link href="/" className="mt-auto rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-slate-800 hover:text-white">New Analysis</Link></aside><main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main></div></div>;
}
