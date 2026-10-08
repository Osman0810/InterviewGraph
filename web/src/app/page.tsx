"use client";

import type { ChangeEvent, DragEvent, FormEvent } from "react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell, Badge, Button, Card } from "../components/ui";
import { apiErrorMessage, networkErrorMessage } from "../lib/api-error";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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
  return file.size > MAX_FILE_BYTES ? "Files must be 5 MB or smaller." : "";
}

function UploadDropzone({ kind, file, disabled, onFile, onRemove }: { kind: UploadKind; file: File | null; disabled: boolean; onFile: (file: File) => void; onRemove: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const rule = rules[kind];
  const select = (candidate?: File) => candidate && onFile(candidate);
  return <div className={`mt-3 rounded-lg border border-dashed p-4 transition ${dragging ? "border-primary bg-primary/10" : "border-app-border bg-slate-950/30 hover:border-slate-600"}`} onDragEnter={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); if (!disabled) setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled) select(event.dataTransfer.files[0]); }}>
    <input ref={input} className="sr-only" type="file" disabled={disabled} accept={kind === "jobDescription" ? ".txt,text/plain" : ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"} aria-label={`Upload ${kind === "jobDescription" ? "job description" : "résumé"}`} onChange={(event: ChangeEvent<HTMLInputElement>) => select(event.target.files?.[0])} />
    {file ? <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-100">{file.name}</p><p className="mt-1 text-xs text-app-muted">{Math.ceil(file.size / 1024)} KB · ready to analyze</p></div><Button variant="ghost" className="px-3 py-2" onClick={onRemove}>Remove</Button></div> : <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-app-muted">Drop a {rule.label} file here, or choose a file to upload.</p><Button variant="secondary" className="shrink-0 px-3 py-2" disabled={disabled} onClick={() => input.current?.click()}>Choose file</Button></div>}
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
      if (!response.ok) {
        setErrors({
          form: apiErrorMessage({
            status: response.status,
            detail: payload.detail,
            operation: "create-session",
          }),
        });
        return;
      }
      router.push(payload.redirect_url);
    } catch {
      setErrors({ form: networkErrorMessage() });
    } finally { setSubmitting(false); }
  };

  const fieldClass = "mt-3 min-h-36 w-full rounded-lg border border-app-border bg-slate-950/30 px-4 py-3 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-primary focus:ring-2 focus:ring-primary/25 disabled:cursor-not-allowed disabled:opacity-50";
  return <AppShell showSidebar={false} topBar={<span className="text-sm text-app-muted">AI interview workspace</span>}><div className="mx-auto max-w-3xl"><header className="mb-8 sm:mb-10"><p className="text-sm font-medium text-indigo-300">InterviewGraph</p><h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">Turn a job description into a targeted technical interview.</h1><p className="mt-3 max-w-2xl text-base leading-7 text-app-muted">Analyze the role against your experience, identify gaps, and practice the areas that matter most.</p></header><Card className="overflow-hidden"><div className="border-b border-app-border px-5 py-5 sm:px-7"><p className="text-xs font-semibold uppercase tracking-[.14em] text-indigo-300">New analysis</p><p className="mt-2 text-sm text-app-muted">Add the role and your experience to create a session.</p></div><form onSubmit={submit} noValidate className="space-y-8 p-5 sm:p-7"><fieldset><legend className="text-base font-semibold text-white">Job Description</legend><p className="mt-1 text-sm text-app-muted">Paste the role details or upload a TXT file.</p><textarea value={jobDescription} disabled={Boolean(jdFile) || submitting} onChange={(event) => { setJobDescription(event.target.value); setJdFile(null); }} aria-describedby="job-description-help" className={fieldClass} placeholder="Paste the job description here…" /><div id="job-description-help" className="mt-2 flex justify-between text-xs text-app-muted"><span>TXT · maximum 5 MB</span><span>{jobDescription.length.toLocaleString()} characters</span></div><UploadDropzone kind="jobDescription" file={jdFile} disabled={submitting} onFile={(file) => upload("jobDescription", file)} onRemove={() => setJdFile(null)} />{errors.jobDescription ? <p className="mt-3 text-sm text-rose-300" role="alert">{errors.jobDescription}</p> : null}</fieldset><fieldset><legend className="text-base font-semibold text-white">Resume</legend><p className="mt-1 text-sm text-app-muted">Paste your experience or upload a PDF or DOCX.</p><textarea value={resume} disabled={Boolean(resumeFile) || submitting} onChange={(event) => { setResume(event.target.value); setResumeFile(null); }} aria-describedby="resume-help" className={fieldClass} placeholder="Paste your experience, skills, and projects here…" /><div id="resume-help" className="mt-2 flex justify-between text-xs text-app-muted"><span>PDF or DOCX · maximum 5 MB</span><span>{resume.length.toLocaleString()} characters</span></div><UploadDropzone kind="resume" file={resumeFile} disabled={submitting} onFile={(file) => upload("resume", file)} onRemove={() => setResumeFile(null)} />{errors.resume ? <p className="mt-3 text-sm text-rose-300" role="alert">{errors.resume}</p> : null}</fieldset><fieldset disabled={submitting}><legend className="text-base font-semibold text-white">AI Provider</legend><p className="mt-1 text-sm text-app-muted">This provider is pinned to the session. Model selection is managed by the service.</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{providers.map((option) => { const selected = provider === option.id; return <label key={option.id} className={`cursor-pointer rounded-lg border p-4 transition focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary ${selected ? "border-primary bg-primary/10" : "border-app-border bg-slate-950/20 hover:border-slate-600"}`}><input className="sr-only" type="radio" name="ai_provider" value={option.id} checked={selected} onChange={() => setProvider(option.id)} /><span className="flex items-start justify-between gap-3"><span><span className="block text-sm font-semibold text-white">{option.name}</span><span className="mt-2 block text-xs leading-5 text-app-muted">{option.description}</span></span>{selected ? <Badge tone="primary">Selected</Badge> : null}</span></label>; })}</div></fieldset>{errors.form ? <div className="rounded-lg border border-rose-400/30 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100" role="alert">{errors.form}</div> : null}<div className="border-t border-app-border pt-5"><Button type="submit" disabled={submitting} className="w-full py-3.5">{submitting ? "Creating analysis..." : "Analyze Role"}</Button></div></form></Card></div></AppShell>;
}
