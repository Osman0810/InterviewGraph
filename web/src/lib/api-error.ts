export type ApiOperation =
  | "create-session"
  | "analysis"
  | "interview"
  | "answer-evaluation"
  | "knowledge-gaps"
  | "study-plan"
  | "replay"
  | "results";

const fallbackByOperation: Record<ApiOperation, string> = {
  "create-session": "Unable to create the analysis session.",
  analysis: "Unable to complete the analysis.",
  interview: "Unable to prepare the interview.",
  "answer-evaluation": "Unable to evaluate your answer.",
  "knowledge-gaps": "Unable to calculate knowledge gaps.",
  "study-plan": "Unable to create the study plan.",
  replay: "Unable to evaluate your improved answer.",
  results: "No analysis results are available yet.",
};

function looksLikeStorageFailure(detail: string) {
  return /database|storage|persist|sqlite|sql|record|session (?:store|storage|persistence)/i.test(detail);
}

function looksLikeProviderFailure(detail: string) {
  return /ai|provider|model|gemini|openai|quota|rate limit|llm/i.test(detail);
}

export function apiErrorMessage({
  status,
  detail,
  operation,
}: {
  status?: number;
  detail?: unknown;
  operation: ApiOperation;
}) {
  const safeDetail = typeof detail === "string" ? detail.trim() : "";

  if (status === 404 && operation === "results")
    return "No analysis results are available yet.";

  if (status === 429)
    return "AI usage limit reached. Please try again later.";

  if (status === 503) {
    if (looksLikeStorageFailure(safeDetail)) {
      return operation === "create-session"
        ? "Unable to create the analysis session."
        : fallbackByOperation[operation];
    }
    if (looksLikeProviderFailure(safeDetail))
      return "AI service is temporarily unavailable. Please try again shortly.";
  }

  if (status === 504)
    return operation === "results"
      ? fallbackByOperation[operation]
      : "AI request timed out. Please try again.";

  if ((status === 400 || status === 422) && safeDetail) {
    return safeDetail;
  }

  return fallbackByOperation[operation];
}

export function networkErrorMessage() {
  return "Unable to reach the InterviewGraph API.";
}
