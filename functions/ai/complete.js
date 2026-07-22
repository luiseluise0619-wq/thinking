// Cloudflare Pages Function — 키를 숨기는 stateless Gemini 프록시.
// 라우트: /ai/complete (파일 경로가 곧 라우트).  정적 index.html 은 Pages 가 자동 서빙.
// 환경변수: GEMINI_API_KEY (Pages → Settings → Environment variables / secret).
export async function onRequestPost({ request, env }) {
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

  const key = env.GEMINI_API_KEY;
  if (!key) return json({ error: "no_provider" }, 503);   // 프론트는 규칙 기반으로 폴백

  let body;
  try { body = await request.json(); } catch { return json({ error: "bad_request" }, 400); }
  if (!(body.user || "").trim()) return json({ error: "user is empty" }, 400);

  const model = env.THINKOS_GEMINI_MODEL || "gemini-2.5-flash";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: body.system || "" }] },
      contents: [{ role: "user", parts: [{ text: body.user || "" }] }],
      generationConfig: { maxOutputTokens: body.max_tokens || 800, temperature: 0.7 },
    }),
  });
  if (!res.ok) return json({ error: "llm_error" }, 502);
  const data = await res.json();
  const text = ((data.candidates?.[0]?.content?.parts) || [])
    .map((p) => p.text || "").join("").trim();
  return json({ text, provider: "gemini" });
}
