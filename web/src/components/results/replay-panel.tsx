import { Button, Card, EmptyState } from "../ui";

type ReplayResult = {
  original_score: number;
  new_score: number;
  improvement: number;
  concepts_corrected: string[];
  concepts_still_missing: string[];
  new_feedback: string;
  improved_answer_outline: string[];
};

type ReplayItem = {
  question_id: string;
  competency_name: string;
  question: string;
  score: number;
  missing_concepts: string[];
  replay_attempts: ReplayResult[];
};

type ReplayPanelProps = {
  items: ReplayItem[];
  answers: Record<string, string>;
  results: Record<string, ReplayResult>;
  loadingId: string | null;
  onAnswer: (id: string, value: string) => void;
  onReplay: (id: string) => void;
};

export function ReplayPanel({
  items,
  answers,
  results,
  loadingId,
  onAnswer,
  onReplay,
}: ReplayPanelProps) {
  const replayable = items.filter(
    (item) => item.score < 70 || item.missing_concepts.length > 0,
  );

  return (
    <Card className="p-5 sm:p-6">
      <h2 className="text-xl font-semibold text-white">Interview Replay</h2>
      <p className="mt-1 text-sm text-app-muted">
        Retry weak questions without changing your original assessment.
      </p>

      {!replayable.length ? (
        <div className="mt-6">
          <EmptyState
            title="No replay attempts yet"
            description="Replay becomes available for questions that need more practice."
          />
        </div>
      ) : (
        <div className="mt-6 space-y-5">
          {replayable.map((item) => {
            const replayed =
              results[item.question_id] ?? item.replay_attempts.at(-1);
            const improved = (replayed?.improvement ?? 0) >= 0;

            return (
              <article
                key={item.question_id}
                className="rounded-xl border border-app-border bg-slate-950/20 p-4 sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[.12em] text-indigo-300">
                      {item.competency_name}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-slate-100">
                      {item.question}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-md bg-slate-800 px-2.5 py-1 text-sm font-semibold text-slate-100">
                    Original {Math.round(item.score)}%
                  </span>
                </div>

                <label
                  className="mt-5 block text-sm font-medium text-slate-200"
                  htmlFor={`replay-answer-${item.question_id}`}
                >
                  Improved Answer
                </label>
                <textarea
                  id={`replay-answer-${item.question_id}`}
                  value={answers[item.question_id] ?? ""}
                  onChange={(event) =>
                    onAnswer(item.question_id, event.target.value)
                  }
                  className="mt-2 min-h-32 w-full rounded-lg border border-app-border bg-slate-950/30 p-3 text-sm leading-6 text-slate-100 outline-none focus:border-primary focus:ring-2 focus:ring-primary/25"
                  placeholder="Write an improved answer…"
                />
                <Button
                  variant="secondary"
                  className="mt-3"
                  onClick={() => onReplay(item.question_id)}
                  disabled={
                    !answers[item.question_id]?.trim() ||
                    loadingId === item.question_id
                  }
                >
                  {loadingId === item.question_id
                    ? "Evaluating your improved answer..."
                    : "Retry Question"}
                </Button>

                {replayed ? (
                  <>
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <ScoreCard
                        label="Original Score"
                        value={replayed.original_score}
                      />
                      <ScoreCard label="New Score" value={replayed.new_score} />
                      <ScoreCard
                        label="Improvement"
                        value={replayed.improvement}
                        improvement={improved}
                      />
                    </div>

                    <div className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
                      {replayed.concepts_corrected.length ? (
                        <FeedbackList
                          label="Concepts corrected"
                          items={replayed.concepts_corrected}
                          tone="success"
                        />
                      ) : null}
                      {replayed.concepts_still_missing.length ? (
                        <FeedbackList
                          label="Concepts still missing"
                          items={replayed.concepts_still_missing}
                          tone="warning"
                        />
                      ) : null}
                      {replayed.new_feedback ? (
                        <section className="sm:col-span-2">
                          <p className="font-medium text-slate-200">Feedback</p>
                          <p className="mt-2 leading-6 text-app-muted">
                            {replayed.new_feedback}
                          </p>
                        </section>
                      ) : null}
                      {replayed.improved_answer_outline.length ? (
                        <FeedbackList
                          label="Improved answer outline"
                          items={replayed.improved_answer_outline}
                          className="sm:col-span-2"
                        />
                      ) : null}
                    </div>
                  </>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function ScoreCard({
  label,
  value,
  improvement,
}: {
  label: string;
  value: number;
  improvement?: boolean;
}) {
  const tone =
    improvement === undefined
      ? "bg-slate-800/60 text-white"
      : improvement
        ? "bg-success/10 text-green-200"
        : "bg-amber-400/10 text-amber-100";
  const sign = label === "Improvement" && value >= 0 ? "+" : "";
  const suffix = label === "Improvement" ? "" : "%";

  return (
    <div className={`rounded-lg p-3 ${tone}`}>
      <p className="text-xs text-app-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">
        {sign}
        {Math.round(value)}
        {suffix}
      </p>
    </div>
  );
}

function FeedbackList({
  label,
  items,
  tone,
  className,
}: {
  label: string;
  items: string[];
  tone?: "success" | "warning";
  className?: string;
}) {
  return (
    <section className={className}>
      <p
        className={
          tone === "success"
            ? "font-medium text-green-200"
            : tone === "warning"
              ? "font-medium text-amber-100"
              : "font-medium text-slate-200"
        }
      >
        {label}
      </p>
      <ul className="mt-2 space-y-1 text-app-muted">
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </section>
  );
}
