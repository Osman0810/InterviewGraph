"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Badge, Button, Card, ErrorState, LoadingState, ProgressBar } from "../../../../components/ui";
import { apiErrorMessage, networkErrorMessage, type ApiOperation } from "../../../../lib/api-error";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Question = { id: string; competency: string; question: string; difficulty: number; type: string; sequence_number: number };
type Progress = { status: "in_progress" | "awaiting_evaluation" | "completed"; question_limit: number; question: Question | null };
type Evaluation = { overall_score: number; feedback: string; strengths: string[]; missing_concepts: string[]; suggested_better_answer_outline: string[] };
const difficulty = ["", "Fundamentals", "Practical", "Implementation", "Architecture & system design"];

async function request(path: string, operation: ApiOperation, options?: RequestInit) {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) } });
  } catch {
    throw new Error(networkErrorMessage());
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiErrorMessage({ status: response.status, detail: body.detail, operation }));
  return body;
}

export default function InterviewPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [progress, setProgress] = useState<Progress | null>(null);
  const [answer, setAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [provider, setProvider] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [confirmEnd, setConfirmEnd] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    void Promise.all([request(`/sessions/${sessionId}/interview/start`, "interview", { method: "POST" }), request(`/sessions/${sessionId}/analysis-summary`, "interview")]).then(([interview, summary]) => { if (active) { setProgress(interview); setProvider(summary.ai_provider ?? ""); } }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to prepare the interview."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sessionId]);

  const submit = async () => {
    if (!progress?.question || !answer.trim() || submitting) return;
    setSubmitting(true); setError("");
    try { setEvaluation(await request(`/sessions/${sessionId}/questions/${progress.question.id}/answer`, "answer-evaluation", { method: "POST", body: JSON.stringify({ answer_text: answer.trim() }) })); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to evaluate your answer."); }
    finally { setSubmitting(false); }
  };
  const next = async () => {
    setLoading(true); setError("");
    try { setProgress(await request(`/sessions/${sessionId}/interview/next-question`, "interview")); setAnswer(""); setEvaluation(null); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load the next question."); }
    finally { setLoading(false); }
  };
  const end = async () => {
    setLoading(true); setConfirmEnd(false);
    try { setProgress(await request(`/sessions/${sessionId}/interview/end`, "interview", { method: "POST" })); setEvaluation(null); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to end the interview."); }
    finally { setLoading(false); }
  };

  if (loading && !progress) return <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center"><LoadingState label="Preparing your interview..." /></div>;
  if (progress?.status === "completed") return <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center"><Card className="w-full p-8 text-center"><p className="text-xs font-semibold uppercase tracking-[.16em] text-indigo-300">Interview complete</p><h1 className="mt-3 text-2xl font-bold text-white">Your responses are saved.</h1><p className="mt-3 text-sm leading-6 text-app-muted">Your deterministic scores are ready to review.</p><Link href={`/session/${sessionId}/results`} className="mt-6 inline-flex rounded-lg bg-primary-strong px-4 py-3 text-sm font-semibold text-white">View results</Link></Card></div>;

  const question = progress?.question;
  const completedPercent = question && progress ? (question.sequence_number / progress.question_limit) * 100 : 0;
  return <section className="mx-auto max-w-4xl"><header className="flex flex-wrap items-start justify-between gap-4 border-b border-app-border pb-5"><div><p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">Technical Interview</p><h1 className="mt-2 text-2xl font-bold tracking-tight text-white">Question {question?.sequence_number ?? "—"} of {progress?.question_limit ?? "—"}</h1></div><div className="flex items-center gap-3">{provider ? <Badge tone="primary" className="font-mono uppercase tracking-wide">{provider}</Badge> : null}<Button variant="ghost" onClick={() => setConfirmEnd(true)} disabled={loading || submitting}>End interview</Button></div><div className="w-full"><ProgressBar value={completedPercent} label={`Interview progress: question ${question?.sequence_number ?? 0} of ${progress?.question_limit ?? 0}`} /><p className="mt-2 text-xs text-app-muted">Question {question?.sequence_number ?? "—"} of {progress?.question_limit ?? "—"}</p></div></header>{error ? <div className="mt-5"><ErrorState title="Interview needs attention" description={error} action={<Link href="/" className="inline-flex items-center rounded-lg bg-primary-strong px-4 py-2.5 text-sm font-semibold text-white">Start a new analysis</Link>} /></div> : null}{question ? <div className="mt-7"><div className="flex flex-wrap gap-2"><Badge tone="primary">Competency · {question.competency}</Badge><Badge>{difficulty[question.difficulty] ?? "Technical"}</Badge></div><h2 className="mt-5 max-w-3xl text-2xl font-semibold leading-9 tracking-tight text-white sm:text-3xl">{question.question}</h2>{!evaluation ? <div className="mt-8"><label htmlFor="answer" className="text-sm font-semibold text-slate-100">Your answer</label><p className="mt-1 text-sm text-app-muted">Explain your approach, tradeoffs, and validation steps. Code-like detail is welcome.</p><textarea id="answer" value={answer} onChange={(event) => setAnswer(event.target.value)} disabled={submitting || loading} className="mt-3 min-h-64 w-full rounded-xl border border-app-border bg-slate-950/35 px-4 py-4 font-mono text-sm leading-7 text-slate-100 outline-none placeholder:font-sans placeholder:text-slate-600 focus:border-primary focus:ring-2 focus:ring-primary/25 disabled:opacity-50" placeholder="Write your answer here…" /><Button className="mt-5 w-full py-3.5 sm:w-auto sm:min-w-48" onClick={() => void submit()} disabled={!answer.trim() || submitting || loading}>{submitting ? "Evaluating your answer..." : "Submit Answer"}</Button></div> : <Card className="mt-8 p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-5"><div><p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">Answer feedback</p><h3 className="mt-2 text-xl font-semibold text-white">What to carry forward</h3></div><div className="text-right"><p className="text-xs font-medium uppercase tracking-wide text-app-muted">Score</p><p className="mt-1 text-3xl font-bold text-white">{Math.round(evaluation.overall_score)}<span className="text-base font-medium text-app-muted"> / 100</span></p></div></div><div className="mt-6 grid gap-4 sm:grid-cols-2"><section className="rounded-lg border border-success/20 bg-success/10 p-4"><h4 className="text-sm font-semibold text-green-200">Strengths</h4><ul className="mt-3 space-y-2 text-sm text-slate-200">{evaluation.strengths.length ? evaluation.strengths.map((item) => <li key={item}>• {item}</li>) : <li>—</li>}</ul></section><section className="rounded-lg border border-amber-400/20 bg-amber-400/10 p-4"><h4 className="text-sm font-semibold text-amber-100">Missing concepts</h4><ul className="mt-3 space-y-2 text-sm text-slate-200">{evaluation.missing_concepts.length ? evaluation.missing_concepts.map((item) => <li key={item}>• {item}</li>) : <li>—</li>}</ul></section></div><section className="mt-5"><h4 className="text-sm font-semibold text-slate-100">Feedback</h4><p className="mt-2 text-sm leading-6 text-app-muted">{evaluation.feedback}</p></section><Button className="mt-6 w-full py-3.5 sm:w-auto sm:min-w-48" onClick={() => void next()} disabled={loading}>{loading ? "Preparing next question..." : "Next Question"}</Button></Card>}</div> : null}{progress?.status === "awaiting_evaluation" ? <p className="mt-6 rounded-lg border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100">This question is awaiting evaluation. Submit the answer before continuing.</p> : null}{confirmEnd ? <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="end-title"><Card className="w-full max-w-sm p-6"><h2 id="end-title" className="text-xl font-semibold text-white">End this interview?</h2><p className="mt-3 text-sm leading-6 text-app-muted">Completed answers are saved. No more questions can be added after ending.</p><div className="mt-6 flex justify-end gap-3"><Button variant="ghost" onClick={() => setConfirmEnd(false)}>Cancel</Button><Button variant="danger" onClick={() => void end()}>End Interview</Button></div></Card></div> : null}</section>;
}
