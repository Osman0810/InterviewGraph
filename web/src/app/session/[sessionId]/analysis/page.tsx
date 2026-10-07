"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Competency = { name: string; category: string; importance: number };
type Summary = { ai_provider?: "gemini" | "openai"; competencies: Competency[]; resume_analysis_complete: boolean };

function safeMessage(message: string) {
  const value = message.toLowerCase();
  if (value.includes("429") || value.includes("rate limit")) return "AI usage limit reached. Please try again later or start a new session with another available provider.";
  if (value.includes("503") || value.includes("unavailable")) return "AI service is temporarily unavailable. Please try again shortly.";
  if (value.includes("504") || value.includes("timed out")) return "The AI request timed out. Please try again.";
  return message;
}
async function request(path: string, method = "GET"): Promise<Summary> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(safeMessage(payload.detail ?? "Analysis could not be completed."));
  return payload as Summary;
}
function ProviderBadge({ provider }: { provider?: string }) {
  if (!provider) return null;
  return <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 font-mono text-xs font-bold uppercase tracking-wide text-emerald-200">{provider}</span>;
}

export default function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [stage, setStage] = useState<"role" | "resume">("role");
  const [error, setError] = useState("");
  const [showSkipConfirmation, setShowSkipConfirmation] = useState(false);
  const [skipLoading, setSkipLoading] = useState(false);
  const [skipError, setSkipError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        let current = await request(`/sessions/${sessionId}/analysis-summary`);
        if (!current.competencies.length) { setStage("role"); await request(`/sessions/${sessionId}/analyze-jd`, "POST"); current = await request(`/sessions/${sessionId}/analysis-summary`); }
        if (!current.resume_analysis_complete) { setStage("resume"); await request(`/sessions/${sessionId}/analyze-resume`, "POST"); current = await request(`/sessions/${sessionId}/analysis-summary`); }
        if (!cancelled) setSummary(current);
      } catch (caught) { if (!cancelled) setError(caught instanceof Error ? caught.message : "Analysis could not be completed."); }
    };
    if (sessionId) void run();
    return () => { cancelled = true; };
  }, [sessionId]);

  const confirmResumeOnly = async () => {
    setSkipLoading(true); setSkipError("");
    try { await request(`/sessions/${sessionId}/resume-only`, "POST"); router.push(`/session/${sessionId}/results`); }
    catch (caught) { setSkipError(caught instanceof Error ? safeMessage(caught.message) : "Résumé-based results could not be created."); }
    finally { setSkipLoading(false); }
  };

  if (error) return <main className="grid min-h-screen place-items-center bg-[#07110f] px-4 text-slate-100"><section className="w-full max-w-lg rounded-2xl border border-rose-400/30 bg-[#0b1916] p-7 shadow-2xl shadow-black/25"><p className="font-mono text-xs font-bold uppercase tracking-[.16em] text-rose-300">Analysis paused</p><h1 className="mt-3 text-3xl font-bold tracking-tight text-white">We couldn’t complete this analysis.</h1><p className="mt-4 text-sm leading-6 text-slate-300">{error}</p><div className="mt-7 flex flex-wrap gap-3"><Link href="/" className="rounded-xl bg-emerald-300 px-4 py-3 text-sm font-bold text-[#07110f]">Start a new analysis</Link><button type="button" onClick={() => { setError(""); setSummary(null); }} className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-bold text-slate-200">Try again</button></div></section></main>;
  if (!summary) return <main className="grid min-h-screen place-items-center bg-[#07110f] px-4 text-slate-100"><section className="w-full max-w-lg rounded-2xl border border-slate-800 bg-[#0b1916] p-8"><div className="flex items-center gap-4"><div className="size-9 animate-spin rounded-full border-2 border-slate-700 border-t-emerald-300" aria-hidden="true" /><div><p className="font-mono text-xs font-bold uppercase tracking-[.16em] text-emerald-300">Analysis in progress</p><h1 className="mt-1 text-xl font-bold text-white">{stage === "role" ? "Analyzing role requirements..." : "Analyzing résumé evidence..."}</h1></div></div><p className="mt-6 text-sm leading-6 text-slate-400">We’re building an evidence-led competency map. Provider details remain pinned to this session.</p></section></main>;

  return <main className="min-h-screen bg-[#07110f] px-4 py-6 text-slate-100 sm:px-6 lg:py-10"><section className="mx-auto max-w-5xl"><header className="flex items-center justify-between border-b border-slate-800 pb-5"><Link href="/" className="inline-flex items-center gap-3 font-bold"><span className="grid size-8 place-items-center rounded-lg bg-emerald-300 font-mono text-xs text-[#07110f]">IG</span>InterviewGraph</Link><ProviderBadge provider={summary.ai_provider} /></header><div className="mt-8 rounded-2xl border border-slate-700 bg-[#0b1916] p-6 shadow-2xl shadow-black/20 sm:p-9"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="font-mono text-xs font-bold uppercase tracking-[.16em] text-emerald-300">Role analysis complete</p><h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">Your technical path is ready.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Detected requirements are organized by role importance. Choose a verification path next; the provider is locked for this session.</p></div><span className="rounded-xl border border-slate-700 px-3 py-2 font-mono text-xs text-slate-400">{summary.competencies.length} signals</span></div><div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Detected competencies">{summary.competencies.map((item) => <article key={`${item.category}-${item.name}`} className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"><div className="flex justify-between gap-3"><div><h2 className="font-semibold text-white">{item.name}</h2><p className="mt-1 text-xs text-slate-500">{item.category}</p></div><span className="font-mono text-sm font-bold text-emerald-300">{item.importance}/5</span></div></article>)}</div><aside className="mt-7 rounded-xl border border-amber-300/20 bg-amber-300/10 p-4 text-sm leading-6 text-amber-100"><strong>Résumé evidence is not verified knowledge.</strong> Missing evidence means the skill was not demonstrated in the submitted résumé, not that you lack it.</aside><div className="mt-8 grid gap-4 md:grid-cols-2"><Link href={`/session/${sessionId}/interview`} className="group rounded-xl bg-emerald-300 p-5 text-[#07110f] transition hover:bg-emerald-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"><p className="font-mono text-xs font-bold uppercase tracking-[.14em]">Start interview</p><p className="mt-3 text-sm leading-6">Answer adaptive questions to measure demonstrated knowledge.</p><span className="mt-5 inline-block text-sm font-bold">Begin interview →</span></Link><button type="button" onClick={() => { setSkipError(""); setShowSkipConfirmation(true); }} className="rounded-xl border border-slate-700 bg-slate-950/40 p-5 text-left transition hover:border-slate-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300"><p className="font-mono text-xs font-bold uppercase tracking-[.14em] text-slate-200">Skip interview</p><p className="mt-3 text-sm leading-6 text-slate-400">Estimate preparation from résumé evidence without asking technical questions.</p><span className="mt-5 inline-block text-sm font-bold text-slate-100">Review evidence →</span></button></div></div>{showSkipConfirmation ? <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 px-4" role="dialog" aria-modal="true" aria-labelledby="skip-title"><section className="w-full max-w-xl rounded-2xl border border-slate-700 bg-[#0b1916] p-6 shadow-2xl"><p className="font-mono text-xs font-bold uppercase tracking-[.14em] text-emerald-300">Résumé evidence only</p><h2 id="skip-title" className="mt-3 text-2xl font-bold text-white">Skip technical interview?</h2><p className="mt-4 text-sm leading-6 text-slate-400">InterviewGraph will estimate preparation using résumé evidence compared with the role. Résumés do not contain everything a candidate knows, so this is not a verified technical assessment.</p>{skipError ? <p className="mt-4 rounded-xl bg-rose-400/10 p-3 text-sm text-rose-200" role="alert">{skipError}</p> : null}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={() => setShowSkipConfirmation(false)} disabled={skipLoading} className="rounded-xl px-4 py-3 text-sm font-bold text-slate-300">Return to Interview</button><button type="button" onClick={() => void confirmResumeOnly()} disabled={skipLoading} className="rounded-xl bg-emerald-300 px-4 py-3 text-sm font-bold text-[#07110f] disabled:opacity-60">{skipLoading ? "Creating results..." : "Analyze Resume Instead"}</button></div></section></div> : null}</section></main>;
}
