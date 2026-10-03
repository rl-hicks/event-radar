export interface MeResponse {
  id: string;
  email: string | null;
  created_at: string;
  database_roundtrip: boolean;
}

const apiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");

export async function fetchMe(accessToken: string): Promise<MeResponse> {
  if (!apiUrl) {
    throw new Error("VITE_API_URL is not configured.");
  }
  const response = await fetch(apiUrl + "/api/me", {
    headers: { Authorization: "Bearer " + accessToken },
  });
  if (!response.ok) {
    throw new Error("Backend identity check failed.");
  }
  return (await response.json()) as MeResponse;
}
