"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Badge, Button, Card, ErrorState, LoadingState, MetricCard, PageHeader } from "../../../../components/ui";
import { apiErrorMessage, networkErrorMessage, type ApiOperation } from "../../../../lib/api-error";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Competency = { name: string; category: string; importance: number };
type Summary = { ai_provider?: "gemini" | "openai"; competencies: Competency[]; resume_analysis_complete: boolean };

async function request(path: string, operation: ApiOperation, method = "GET"): Promise<Summary> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, cache: "no-store" });
  } catch {
    throw new Error(networkErrorMessage());
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiErrorMessage({ status: response.status, detail: payload.detail, operation }));
  return payload as Summary;
}

function importanceLabel(value: number) {
  return value >= 5 ? "Critical" : value >= 4 ? "High" : value >= 3 ? "Moderate" : "Supporting";
}

function importanceTone(value: number): "danger" | "warning" | "primary" | "neutral" {
  return value >= 5 ? "danger" : value >= 4 ? "warning" : value >= 3 ? "primary" : "neutral";
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
        let current = await request(`/sessions/${sessionId}/analysis-summary`, "analysis");
        if (!current.competencies.length) { setStage("role"); await request(`/sessions/${sessionId}/analyze-jd`, "analysis", "POST"); current = await request(`/sessions/${sessionId}/analysis-summary`, "analysis"); }
        if (!current.resume_analysis_complete) { setStage("resume"); await request(`/sessions/${sessionId}/analyze-resume`, "analysis", "POST"); current = await request(`/sessions/${sessionId}/analysis-summary`, "analysis"); }
        if (!cancelled) setSummary(current);
      } catch (caught) { if (!cancelled) setError(caught instanceof Error ? caught.message : "Analysis could not be completed."); }
    };
    if (sessionId) void run();
    return () => { cancelled = true; };
  }, [sessionId]);

  const confirmResumeOnly = async () => {
    setSkipLoading(true); setSkipError("");
    try { await request(`/sessions/${sessionId}/resume-only`, "knowledge-gaps", "POST"); router.push(`/session/${sessionId}/results`); }
    catch (caught) { setSkipError(caught instanceof Error ? caught.message : "Unable to calculate knowledge gaps."); }
    finally { setSkipLoading(false); }
  };

  const priorityAreas = useMemo(() => summary?.competencies.filter((item) => item.importance >= 4).length ?? 0, [summary]);

  if (error) return <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center"><ErrorState title="We couldn’t complete this analysis." description={error} action={<><Link href="/" className="inline-flex items-center rounded-lg bg-primary-strong px-4 py-2.5 text-sm font-semibold text-white">Start a new analysis</Link><Button variant="secondary" onClick={() => { setError(""); setSummary(null); }}>Try again</Button></>} /></div>;
  if (!summary) return <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center"><div className="w-full"><LoadingState label={stage === "role" ? "Analyzing role requirements..." : "Analyzing résumé evidence..."} /><p className="mt-4 text-center text-sm text-app-muted">We’re building your role competency map from the submitted job description and résumé.</p></div></div>;

  return <section className="mx-auto max-w-6xl"><PageHeader eyebrow="Role Analysis" title="Role Analysis" description="How your experience maps to the requirements of this role." action={summary.ai_provider ? <Badge tone="primary" className="font-mono uppercase tracking-wide">{summary.ai_provider}</Badge> : null} /><div className="mt-6 grid gap-4 sm:grid-cols-2"><MetricCard label="Role competencies" value={summary.competencies.length} detail="Requirements identified from the job description." /><MetricCard label="Priority areas" value={priorityAreas} detail="Competencies marked high or critical for this role." /></div><Card className="mt-6"><div className="flex flex-wrap items-center justify-between gap-4 border-b border-app-border p-5 sm:px-6"><div><h2 className="text-lg font-semibold text-white">Role competencies</h2><p className="mt-1 text-sm text-app-muted">Requirements organized by job-description importance.</p></div><Badge tone={summary.resume_analysis_complete ? "success" : "neutral"}>{summary.resume_analysis_complete ? "Résumé evidence analyzed" : "Résumé evidence pending"}</Badge></div><div className="divide-y divide-app-border">{summary.competencies.map((item) => <article key={`${item.category}-${item.name}`} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><h3 className="font-semibold text-white">{item.name}</h3><p className="mt-1 text-sm text-app-muted">{item.category}</p></div><div className="flex items-center gap-3"><span className="text-xs text-app-muted">Importance</span><Badge tone={importanceTone(item.importance)}>{importanceLabel(item.importance)}</Badge></div></article>)}</div></Card><section className="mt-6 grid gap-4 lg:grid-cols-2"><Card className="p-5 sm:p-6"><p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">Start Interview</p><h2 className="mt-2 text-lg font-semibold text-white">Validate your knowledge through adaptive technical questions.</h2><p className="mt-2 text-sm leading-6 text-app-muted">Your provider remains pinned to this session while questions are generated and evaluated.</p><Link href={`/session/${sessionId}/interview`} className="mt-5 inline-flex w-full items-center justify-center rounded-lg bg-primary-strong px-4 py-3 text-sm font-semibold text-white transition hover:bg-primary">Start Interview</Link></Card><Card className="p-5 sm:p-6"><p className="text-xs font-semibold uppercase tracking-[.14em] text-slate-300">Skip Interview</p><h2 className="mt-2 text-lg font-semibold text-white">Generate a résumé-evidence-based gap assessment.</h2><p className="mt-2 text-sm leading-6 text-app-muted">This view compares submitted résumé evidence with the role; it does not verify technical knowledge.</p><Button variant="secondary" className="mt-5 w-full py-3" onClick={() => { setSkipError(""); setShowSkipConfirmation(true); }}>Skip Interview</Button></Card></section>{showSkipConfirmation ? <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 px-4" role="dialog" aria-modal="true" aria-labelledby="skip-title"><Card className="w-full max-w-xl p-6"><p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">Résumé evidence only</p><h2 id="skip-title" className="mt-3 text-xl font-semibold text-white">Skip technical interview?</h2><p className="mt-3 text-sm leading-6 text-app-muted">InterviewGraph will estimate preparation using résumé evidence compared with the role. Résumés do not contain everything a candidate knows, so this is not a verified technical assessment.</p>{skipError ? <p className="mt-4 rounded-lg bg-rose-400/10 p-3 text-sm text-rose-200" role="alert">{skipError}</p> : null}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><Button variant="ghost" onClick={() => setShowSkipConfirmation(false)} disabled={skipLoading}>Return to Interview</Button><Button onClick={() => void confirmResumeOnly()} disabled={skipLoading}>{skipLoading ? "Calculating knowledge gaps..." : "Generate Assessment"}</Button></div></Card></div> : null}</section>;
}
