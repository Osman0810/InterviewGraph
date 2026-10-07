"use client";

import type { ChangeEvent, DragEvent, FormEvent } from "react";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MAX_FILE_BYTES = 5 * 1024 * 1024;
type UploadKind = "jobDescription" | "resume";
type AIProvider = "gemini" | "openai";

const providers: { id: AIProvider; name: string; description: string }[] = [
  { id: "gemini", name: "Gemini", description: "Free-tier availability depends on current API quota." },
  { id: "openai", name: "OpenAI", description: "OpenAI API usage may incur API charges." },
];
const rules = {
  jobDescription: { label: "TXT", extensions: ["txt"], mime: ["text/plain"] },
  resume: { label: "PDF or DOCX", extensions: ["pdf", "docx"], mime: ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"] },
} as const;

function fileError(file: File, kind: UploadKind) {
  const rule = rules[kind];
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !rule.extensions.includes(extension as never)) return `Choose a ${rule.label} file.`;
  if (!rule.mime.includes(file.type as never)) return "The selected file type does not match its extension.";
  if (file.size > MAX_FILE_BYTES) return "Files must be 5 MB or smaller.";
  return "";
}

function providerError(message: string) {
  const lower = message.toLowerCase();
  if (lower.includes("429") || lower.includes("rate limit") || lower.includes("usage limit")) return "AI usage limit reached. Please try again later or start a new session with another available provider.";
  if (lower.includes("503") || lower.includes("unavailable")) return "AI service is temporarily unavailable. Please try again shortly.";
  if (lower.includes("504") || lower.includes("timed out")) return "The AI request timed out. Please try again.";
  return message;
}

function UploadDropzone({ kind, file, disabled, onFile, onRemove }: { kind: UploadKind; file: File | null; disabled: boolean; onFile: (file: File) => void; onRemove: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const rule = rules[kind];
  const select = (candidate?: File) => candidate && onFile(candidate);
  return <div className={`mt-3 rounded-xl border border-dashed p-3 transition ${dragging ? "border-emerald-400 bg-emerald-400/10" : "border-slate-700 bg-slate-950/40 hover:border-slate-600"}`}
    onDragEnter={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); if (!disabled) setDragging(true); }}
    onDragOver={(event) => event.preventDefault()}
    onDragLeave={() => setDragging(false)}
    onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled) select(event.dataTransfer.files[0]); }}>
    <input ref={input} className="sr-only" type="file" disabled={disabled} accept={kind === "jobDescription" ? ".txt,text/plain" : ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"} aria-label={`Upload ${kind === "jobDescription" ? "job description" : "résumé"}`} onChange={(event: ChangeEvent<HTMLInputElement>) => select(event.target.files?.[0])} />
    {file ? <div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-100">{file.name}</p><p className="mt-1 text-xs text-slate-400">{Math.ceil(file.size / 1024)} KB · ready to analyze</p></div><button type="button" onClick={onRemove} className="rounded-lg px-3 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-emerald-400">Remove</button></div> : <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-slate-400">Drop a {rule.label} file here. Maximum 5 MB; source files are not retained.</p><button type="button" disabled={disabled} onClick={() => input.current?.click()} className="shrink-0 rounded-lg border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200 hover:border-slate-500 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50">Browse</button></div>}
  </div>;
}

export default function Home() {
  const router = useRouter();
  const [provider, setProvider] = useState<AIProvider>("gemini");
  const [jobDescription, setJobDescription] = useState("");
  const [resume, setResume] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const upload = (kind: UploadKind, file: File) => {
    const error = fileError(file, kind);
    if (error) { setErrors((current) => ({ ...current, [kind]: error })); return; }
    setErrors((current) => ({ ...current, [kind]: "" }));
    if (kind === "jobDescription") { setJdFile(file); setJobDescription(""); } else { setResumeFile(file); setResume(""); }
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!jobDescription.trim() && !jdFile) next.jobDescription = "Paste a job description or upload a TXT file.";
    if (!resume.trim() && !resumeFile) next.resume = "Paste your résumé or upload a PDF or DOCX file.";
    if (Object.keys(next).length) { setErrors(next); return; }
    setSubmitting(true); setErrors({});
    const body = new FormData();
    body.append("ai_provider", provider);
    if (jdFile) body.append("job_description_file", jdFile); else body.append("job_description_text", jobDescription.trim());
    if (resumeFile) body.append("resume_file", resumeFile); else body.append("resume_text", resume.trim());
    try {
      const response = await fetch(`${API_BASE_URL}/sessions`, { method: "POST", body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) { setErrors({ form: providerError(payload.detail ?? "We could not create your session. Please try again.") }); return; }
      router.push(payload.redirect_url);
    } catch { setErrors({ form: "The API is unavailable. Check that FastAPI is running and try again." }); }
    finally { setSubmitting(false); }
  };

  return <main className="min-h-screen bg-[#07110f] text-slate-100"><div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
    <header className="flex items-center justify-between border-b border-slate-800 pb-5"><Link href="/" className="inline-flex items-center gap-3 font-bold tracking-tight"><span className="grid size-8 place-items-center rounded-lg bg-emerald-400 font-mono text-sm text-[#07110f]">IG</span><span>InterviewGraph</span></Link><span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-xs font-semibold text-emerald-200">Private by design</span></header>
    <div className="grid gap-10 py-10 lg:grid-cols-[.75fr_1.25fr] lg:py-16">
      <section className="lg:sticky lg:top-8 lg:self-start"><p className="font-mono text-xs font-bold uppercase tracking-[.2em] text-emerald-300">Evidence-led interview preparation</p><h1 className="mt-5 max-w-xl text-4xl font-bold tracking-[-.05em] text-white sm:text-6xl">Prepare with signal, not guesswork.</h1><p className="mt-5 max-w-lg text-base leading-7 text-slate-400 sm:text-lg">Map a role to your demonstrated experience, then choose a technical interview or résumé-based analysis. Your source files stay in the API workflow; only extracted text is retained for the session.</p><div className="mt-9 space-y-3">{[["01", "Role requirements", "Bring the job description into focus."], ["02", "Evidence mapping", "Ground analysis in your résumé."], ["03", "Your next move", "Interview or evidence-only results."]].map(([number, title, copy]) => <div key={number} className="flex gap-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4"><span className="font-mono text-xs font-bold text-emerald-300">{number}</span><div><p className="text-sm font-semibold text-slate-100">{title}</p><p className="mt-1 text-sm text-slate-400">{copy}</p></div></div>)}</div></section>
      <form onSubmit={submit} noValidate className="rounded-2xl border border-slate-700 bg-[#0b1916] p-5 shadow-2xl shadow-black/20 sm:p-8"><div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-6"><div><p className="font-mono text-xs font-bold uppercase tracking-[.16em] text-emerald-300">New analysis</p><h2 className="mt-2 text-2xl font-bold tracking-tight text-white">Set the role context</h2><p className="mt-2 text-sm text-slate-400">Choose a provider, then add one source for each section.</p></div><span className="rounded-lg border border-slate-700 px-2.5 py-1 font-mono text-xs text-slate-400">01 / 02</span></div>
        <div className="mt-7 space-y-8"><fieldset disabled={submitting}><legend className="text-sm font-bold uppercase tracking-[.12em] text-slate-200">AI provider</legend><p className="mt-2 text-sm text-slate-400">The provider is pinned to this analysis. The server selects the model.</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{providers.map((option) => { const selected = provider === option.id; return <label key={option.id} className={`cursor-pointer rounded-xl border p-4 transition focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-emerald-400 ${selected ? "border-emerald-400 bg-emerald-400/10" : "border-slate-700 bg-slate-950/30 hover:border-slate-600"}`}><input className="sr-only" type="radio" name="ai_provider" value={option.id} checked={selected} onChange={() => setProvider(option.id)} /><span className="flex items-start justify-between gap-3"><span><span className="block text-sm font-bold text-white">{option.name}</span><span className="mt-2 block text-xs leading-5 text-slate-400">{option.description}</span></span><span aria-hidden="true" className={`mt-0.5 grid size-4 place-items-center rounded-full border ${selected ? "border-emerald-300 bg-emerald-300" : "border-slate-600"}`}>{selected && <span className="size-1.5 rounded-full bg-[#07110f]" />}</span></span></label>; })}</div><p className="mt-3 text-xs text-slate-500">You will choose Start Interview or Skip Interview after role analysis.</p></fieldset>
          <fieldset><legend className="text-sm font-bold uppercase tracking-[.12em] text-slate-200">Job description</legend><p className="mt-2 text-sm text-slate-400">Paste role details or upload plain text.</p><textarea value={jobDescription} disabled={Boolean(jdFile) || submitting} onChange={(event) => { setJobDescription(event.target.value); setJdFile(null); }} aria-describedby="jd-help" className="mt-4 min-h-36 w-full rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-3 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/25 disabled:cursor-not-allowed disabled:opacity-50" placeholder="Paste the job description here…" /><div id="jd-help" className="mt-2 flex justify-between text-xs text-slate-500"><span>Or upload a TXT file</span><span>{jobDescription.length.toLocaleString()} characters</span></div><UploadDropzone kind="jobDescription" file={jdFile} disabled={submitting} onFile={(file) => upload("jobDescription", file)} onRemove={() => setJdFile(null)} />{errors.jobDescription || errors.jobDescriptionFile ? <p className="mt-3 text-sm text-rose-300" role="alert">{errors.jobDescription || errors.jobDescriptionFile}</p> : null}</fieldset>
          <fieldset><legend className="text-sm font-bold uppercase tracking-[.12em] text-slate-200">Current résumé</legend><p className="mt-2 text-sm text-slate-400">Paste your experience or upload a PDF or DOCX.</p><textarea value={resume} disabled={Boolean(resumeFile) || submitting} onChange={(event) => { setResume(event.target.value); setResumeFile(null); }} aria-describedby="resume-help" className="mt-4 min-h-36 w-full rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-3 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/25 disabled:cursor-not-allowed disabled:opacity-50" placeholder="Paste your experience, skills, and projects here…" /><div id="resume-help" className="mt-2 flex justify-between text-xs text-slate-500"><span>Or upload a PDF or DOCX file</span><span>{resume.length.toLocaleString()} characters</span></div><UploadDropzone kind="resume" file={resumeFile} disabled={submitting} onFile={(file) => upload("resume", file)} onRemove={() => setResumeFile(null)} />{errors.resume || errors.resumeFile ? <p className="mt-3 text-sm text-rose-300" role="alert">{errors.resume || errors.resumeFile}</p> : null}</fieldset></div>
        {errors.form ? <div className="mt-6 rounded-xl border border-rose-400/35 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100" role="alert"><p>{errors.form}</p><Link className="mt-2 inline-flex font-semibold underline underline-offset-4" href="/">Start a new session with another provider</Link></div> : null}
        <button type="submit" disabled={submitting} className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-300 px-5 py-3.5 text-sm font-bold text-[#07110f] transition hover:bg-emerald-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 disabled:cursor-wait disabled:bg-slate-600 disabled:text-slate-300">{submitting ? "Creating your analysis…" : "Analyze Role"}<span aria-hidden="true">→</span></button>
      </form>
    </div>
  </div></main>;
}
