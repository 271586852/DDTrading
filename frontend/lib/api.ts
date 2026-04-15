import type { FactorWeights, ScoreResponse } from "@/types/scoring";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010";

export async function fetchScores(
  weights: FactorWeights,
): Promise<ScoreResponse> {
  const response = await fetch(`${API_BASE_URL}/score`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(weights),
    cache: "no-store",
  });

  if (!response.ok) {
    const fallbackMessage = `Scoring request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      throw new Error(payload.detail ?? fallbackMessage);
    } catch {
      throw new Error(fallbackMessage);
    }
  }

  return (await response.json()) as ScoreResponse;
}
