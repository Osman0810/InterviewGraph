"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "../../../../components/ui";
import { ReplayPanel } from "../../../../components/results/replay-panel";
import { StudyPlanPanel } from "../../../../components/results/study-plan-panel";
import { apiErrorMessage, networkErrorMessage } from "../../../../lib/api-error";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Priority = "low" | "medium" | "high" | "critical";
type Tab = "overview" | "gaps" | "feedback" | "plan";
type Competency = {
  competency_id: string;
  name: string;
  category: string;
  importance: number;
  final_score: number;
  confidence: number;
  gap_priority: Priority;
};
type ReplayResult = {
  replay_id: string;
  original_score: number;
  new_score: number;
  improvement: number;
  concepts_corrected: string[];
  concepts_still_missing: string[];
  new_feedback: string;
  improved_answer_outline: string[];
};
type Feedback = {
  question_id: string;
  competency_name: string;
  question: string;
  candidate_answer: string | null;
  score: number;
  strengths: string[];
  missing_concepts: string[];
  improved_answer_outline: string[];
  replay_attempts: ReplayResult[];
};
type StudyTopic = {
  topic: string;
  current_gap: string;
  concepts_to_review: string[];
  hands_on_task: string;
  interview_questions_to_practice: string[];
  estimated_time_minutes: number;
};
type StudyPlan = {
  critical: StudyTopic[];
  important: StudyTopic[];
  optional: StudyTopic[];
};
type Results = {
  ai_provider?: string;
  mode: "interview" | "resume_only";
  label: string;
  overall_readiness: number;
  overall_confidence: number;
  competencies: Competency[];
  strengths: string[];
  priority_gaps: string[];
  interview_feedback: Feedback[];
  study_plan: StudyPlan | null;
};

const rank: Record<Priority, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};
const importance = (value: number) =>
  value >= 5
    ? "Critical"
    : value >= 4
      ? "High"
      : value >= 3
        ? "Moderate"
        : "Supporting";
const confidence = (value: number) =>
  value >= 0.8 ? "High" : value >= 0.5 ? "Medium" : "Low";
const status = (item: Competency) =>
  item.gap_priority === "critical" || item.gap_priority === "high"
    ? "Priority Gap"
    : item.gap_priority === "medium"
      ? "Needs Review"
      : item.final_score >= 80
        ? "Strong"
        : "Good";
const statusTone = (
  item: Competency,
): "success" | "primary" | "warning" | "danger" =>
  item.gap_priority === "critical" || item.gap_priority === "high"
    ? "danger"
    : item.gap_priority === "medium"
      ? "warning"
      : item.final_score >= 80
        ? "success"
        : "primary";
const statusColor = (item: Competency) =>
  statusTone(item) === "danger"
    ? "bg-rose-400"
    : statusTone(item) === "warning"
      ? "bg-amber-400"
      : statusTone(item) === "success"
        ? "bg-success"
        : "bg-primary";
function GapRow({ item }: { item: Competency }) {
  return (
    <article className="grid gap-4 p-5 sm:grid-cols-[minmax(10rem,1.4fr)_minmax(7rem,.8fr)_minmax(8rem,.8fr)_minmax(7rem,.7fr)_auto] sm:items-center sm:px-6">
      <div>
        <h3 className="font-semibold text-white">{item.name}</h3>
        <p className="mt-1 text-sm text-app-muted">{item.category}</p>
      </div>
      <div>
        <p className="text-xl font-semibold text-white">
          {Math.round(item.final_score)}%
        </p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full ${statusColor(item)}`}
            style={{
              width: `${Math.max(0, Math.min(100, item.final_score))}%`,
            }}
          />
        </div>
      </div>
      <p className="text-sm text-slate-300">
        <span className="block text-xs text-app-muted sm:hidden">
          JD importance
        </span>
        {importance(item.importance)} importance
      </p>
      <p className="text-sm text-slate-300">
        <span className="block text-xs text-app-muted sm:hidden">
          Confidence
        </span>
        {confidence(item.confidence)} confidence
      </p>
      <Badge tone={statusTone(item)}>{status(item)}</Badge>
    </article>
  );
}

export default function ResultsPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState("");
  const [replayAnswer, setReplayAnswer] = useState<Record<string, string>>({});
  const [replayResult, setReplayResult] = useState<
    Record<string, ReplayResult>
  >({});
  const [replayLoading, setReplayLoading] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/sessions/${sessionId}/results`, {
      cache: "no-store",
    })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok)
          throw new Error(
            apiErrorMessage({
              status: response.status,
              detail: body.detail,
              operation: "results",
            }),
          );
        if (!cancelled) setResults(body as Results);
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setError(
            caught instanceof TypeError
              ? networkErrorMessage()
              : caught instanceof Error
              ? caught.message
              : "Results could not be loaded.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);
  const generatePlan = async () => {
    if (planLoading || !results) return;
    setPlanLoading(true);
    setPlanError("");
    try {
      const response = await fetch(
        `${API_BASE_URL}/sessions/${sessionId}/study-plan${results.study_plan ? "/regenerate" : ""}`,
        { method: "POST" },
      );
      const body = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          apiErrorMessage({
            status: response.status,
            detail: body.detail,
            operation: "study-plan",
          }),
        );
      setResults((current) =>
        current ? { ...current, study_plan: body.plan as StudyPlan } : current,
      );
    } catch (caught) {
      setPlanError(
        caught instanceof TypeError
          ? networkErrorMessage()
          : caught instanceof Error
          ? caught.message
          : "Study plan could not be generated.",
      );
    } finally {
      setPlanLoading(false);
    }
  };
  const replay = async (questionId: string) => {
    const answer = replayAnswer[questionId]?.trim();
    if (!answer || replayLoading) return;
    setReplayLoading(questionId);
    try {
      const response = await fetch(
        `${API_BASE_URL}/sessions/${sessionId}/questions/${questionId}/replay`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ answer_text: answer }),
        },
      );
      const body = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          apiErrorMessage({
            status: response.status,
            detail: body.detail,
            operation: "replay",
          }),
        );
      setReplayResult((value) => ({
        ...value,
        [questionId]: body as ReplayResult,
      }));
      setReplayAnswer((value) => ({ ...value, [questionId]: "" }));
    } catch (caught) {
      setError(
        caught instanceof TypeError
          ? networkErrorMessage()
          : caught instanceof Error
          ? caught.message
          : "Replay could not be evaluated.",
      );
    } finally {
      setReplayLoading(null);
    }
  };
  const remove = async () => {
    if (
      !window.confirm(
        "Delete this session and all associated data? This cannot be undone.",
      )
    )
      return;
    setDeleteLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Session data could not be deleted.");
      router.push("/");
    } catch (caught) {
      setError(
        caught instanceof TypeError
          ? networkErrorMessage()
          : caught instanceof Error
          ? caught.message
          : "Session data could not be deleted.",
      );
      setDeleteLoading(false);
    }
  };
  const competencies = useMemo(
    () =>
      results
        ? [...results.competencies].sort(
            (a, b) =>
              rank[b.gap_priority] - rank[a.gap_priority] ||
              a.final_score - b.final_score,
          )
        : [],
    [results],
  );

  if (error === "No analysis results are available yet.")
    return (
      <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center">
        <EmptyState
          title="No analysis results yet"
          description="Finish an interview or generate a résumé-based assessment to view your knowledge gaps and readiness."
          action={<Link href={`/session/${sessionId}/analysis`} className="inline-flex items-center rounded-lg bg-primary-strong px-4 py-2.5 text-sm font-semibold text-white">Return to analysis</Link>}
        />
      </div>
    );
  if (error)
    return (
      <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center">
        <ErrorState
          title="We couldn’t load these results."
          description={error}
          action={
            <>
              <Link
                href="/"
                className="inline-flex items-center rounded-lg bg-primary-strong px-4 py-2.5 text-sm font-semibold text-white"
              >
                Start new analysis
              </Link>
              <Button
                variant="secondary"
                onClick={() => {
                  setError("");
                  setResults(null);
                }}
              >
                Try again
              </Button>
            </>
          }
        />
      </div>
    );
  if (!results)
    return (
      <div className="mx-auto grid min-h-[calc(100vh-10rem)] max-w-lg place-items-center">
        <LoadingState label="Reading your saved results..." />
      </div>
    );

  const requestedTab = searchParams.get("tab");
  const activeTab: Tab =
    requestedTab === "plan"
      ? "plan"
      : requestedTab === "replay" && results.mode === "interview"
        ? "feedback"
        : requestedTab === "gaps"
          ? "gaps"
          : requestedTab === "overview"
            ? "overview"
        : tab;

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "gaps", label: "Knowledge Gaps" },
    ...(results.mode === "interview"
      ? [{ id: "feedback" as Tab, label: "Interview Feedback" }]
      : []),
    { id: "plan", label: "Study Plan" },
  ];
  const priorityGaps = competencies
    .filter(
      (item) =>
        item.gap_priority === "critical" || item.gap_priority === "high",
    )
    .slice(0, 3);
  const gapMap = (
    <Card className="overflow-hidden">
      <div className="border-b border-app-border p-5 sm:px-6">
        <h2 className="text-lg font-semibold text-white">Knowledge gap map</h2>
        <p className="mt-1 text-sm text-app-muted">
          Scores, role importance, confidence, and backend-calculated gap
          status.
        </p>
      </div>
      <div className="hidden border-b border-app-border bg-slate-950/20 px-6 py-3 text-xs font-medium uppercase tracking-wide text-app-muted sm:grid sm:grid-cols-[minmax(10rem,1.4fr)_minmax(7rem,.8fr)_minmax(8rem,.8fr)_minmax(7rem,.7fr)_auto]">
        <span>Competency</span>
        <span>Score</span>
        <span>JD importance</span>
        <span>Confidence</span>
        <span>Status</span>
      </div>
      <div className="divide-y divide-app-border">
        {competencies.map((item) => (
          <GapRow key={item.competency_id} item={item} />
        ))}
      </div>
    </Card>
  );

  return (
    <section className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow="Interview Results"
        title="Overall Readiness"
        description={
          results.mode === "resume_only"
            ? "Résumé-Based Assessment — based on submitted evidence, not verified knowledge."
            : "Interview Assessment — combines role requirements, résumé evidence, and interview performance."
        }
        action={
          <div className="text-right">
            <p className="text-4xl font-bold tracking-tight text-white">
              {Math.round(results.overall_readiness)}
              <span className="text-lg text-app-muted">%</span>
            </p>
            <p className="mt-1 text-xs text-app-muted">
              {confidence(results.overall_confidence)} confidence
            </p>
          </div>
        }
      />
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <nav
          className="flex gap-1 overflow-x-auto rounded-lg border border-app-border bg-surface p-1"
          aria-label="Results sections"
        >
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={activeTab === item.id ? "page" : undefined}
              onClick={() => {
                setTab(item.id);
                router.replace(
                  `/session/${sessionId}/results?tab=${item.id === "feedback" ? "replay" : item.id}`,
                );
              }}
              className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition ${activeTab === item.id ? "bg-primary-strong text-white" : "text-app-muted hover:bg-slate-800 hover:text-white"}`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <Button
          variant="danger"
          onClick={() => void remove()}
          disabled={deleteLoading}
        >
          {deleteLoading ? "Deleting..." : "Delete Session Data"}
        </Button>
      </div>
      {activeTab === "overview" ? (
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,.75fr)]">
          <div>{gapMap}</div>
          <aside className="space-y-4">
            <Card className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-rose-300">
                Priority gaps
              </p>
              <ol className="mt-4 space-y-4">
                {priorityGaps.length ? (
                  priorityGaps.map((item, index) => (
                    <li key={item.competency_id} className="flex gap-3">
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-rose-400/10 text-xs font-semibold text-rose-200">
                        {index + 1}
                      </span>
                      <div>
                        <p className="font-medium text-white">{item.name}</p>
                        <p className="mt-1 text-sm text-app-muted">
                          {importance(item.importance)} importance ·{" "}
                          {Math.round(item.final_score)}% score
                        </p>
                      </div>
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-app-muted">
                    No critical or high-priority gaps identified.
                  </li>
                )}
              </ol>
            </Card>
            {results.strengths.length ? (
              <Card className="p-5">
                <p className="text-xs font-semibold uppercase tracking-[.14em] text-green-200">
                  Summary
                </p>
                <ul className="mt-4 space-y-2 text-sm text-slate-200">
                  {results.strengths.slice(0, 3).map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </Card>
            ) : null}
          </aside>
        </div>
      ) : null}
      {activeTab === "gaps" ? <div className="mt-6">{gapMap}</div> : null}
      {activeTab === "feedback" && results.mode === "interview" ? (
        <section className="mt-6 space-y-5">
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold text-white">
              Interview feedback
            </h2>
            <div className="mt-5 space-y-4">
              {results.interview_feedback.map((item, index) => (
                <article
                  key={item.question_id}
                  className="rounded-lg border border-app-border bg-slate-950/20 p-4"
                >
                  <div className="flex flex-wrap justify-between gap-3">
                    <div>
                      <p className="text-xs font-medium text-indigo-300">
                        Question {index + 1} · {item.competency_name}
                      </p>
                      <h3 className="mt-2 font-medium text-white">
                        {item.question}
                      </h3>
                    </div>
                    <p className="text-xl font-semibold text-white">
                      {Math.round(item.score)}%
                    </p>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-app-muted">
                    {item.candidate_answer ?? "Skipped"}
                  </p>
                </article>
              ))}
            </div>
          </Card>
          <ReplayPanel
            items={results.interview_feedback}
            answers={replayAnswer}
            results={replayResult}
            loadingId={replayLoading}
            onAnswer={(id, value) =>
              setReplayAnswer((current) => ({ ...current, [id]: value }))
            }
            onReplay={(id) => void replay(id)}
          />
        </section>
      ) : null}
      {activeTab === "plan" ? (
        <StudyPlanPanel
          plan={results.study_plan}
          loading={planLoading}
          error={planError}
          onGenerate={() => void generatePlan()}
        />
      ) : null}
    </section>
  );
}
