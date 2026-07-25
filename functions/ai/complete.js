// Cloudflare Pages Function — 키를 숨기는 stateless Gemini 프록시.
// 라우트: /ai/complete.  정적 index.html 은 Pages 가 자동 서빙.
// 환경변수: GEMINI_API_KEY (필수), THINKOS_GEMINI_MODEL (선택).
// 모델이 지원 종료돼도 안 깨지도록, 404면 사용 가능한 flash 모델을 자동 선택해 재시도한다.
const GC = "generateContent";

function bestModel(models) {
  const bad = ["vision", "image", "tts", "embedding", "aqa", "thinking", "live"];
  const ok = models.filter((m) => !bad.some((b) => m.includes(b)));
  const flash = ok.filter((m) => m.includes("flash"));
  const pool = flash.length ? flash : ok.length ? ok : models;
  const latest = pool.filter((m) => m.endsWith("-latest"));
  return (latest[0] || pool[0]) || null;
}
async function listModels(key) {
  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${key}`);
  if (!r.ok) return [];
  const d = await r.json();
  return (d.models || []).filter((m) => (m.supportedGenerationMethods || []).includes(GC))
    .map((m) => m.name.split("/").pop());
}
async function generate(key, model, payload) {
  return fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
}

export async function onRequestPost({ request, env }) {
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

  const key = env.GEMINI_API_KEY;
  if (!key) return json({ error: "no_provider" }, 503);
  let body;
  try { body = await request.json(); } catch { return json({ error: "bad_request" }, 400); }
  if (!(body.user || "").trim()) return json({ error: "user is empty" }, 400);

  const payload = {
    contents: [{ role: "user", parts: [{ text: body.user || "" }] }],
    // thinkingBudget:0 → flash가 답변 대신 '사고'에 예산을 쓰다 답이 잘리는 것 방지
    generationConfig: { maxOutputTokens: body.max_tokens || 2048, temperature: 0.7, thinkingConfig: { thinkingBudget: 0 } },
  };
  if ((body.system || "").trim()) payload.systemInstruction = { parts: [{ text: body.system }] };

  let model = env.THINKOS_GEMINI_MODEL || "gemini-flash-latest";
  let triedDiscovery = false, strippedThinking = false;
  for (let attempt = 0; attempt < 4; attempt++) {
    const res = await generate(key, model, payload);
    if (res.ok) {
      const data = await res.json();
      const text = ((data.candidates?.[0]?.content?.parts) || []).map((p) => p.text || "").join("").trim();
      return json({ text, provider: "gemini", model });
    }
    let detail = ""; try { detail = (await res.text()).slice(0, 500); } catch {}
    if (res.status === 404 && !triedDiscovery) {   // 모델 지원 종료 → 자동 탐색
      triedDiscovery = true;
      const pick = bestModel(await listModels(key));
      if (pick && pick !== model) { model = pick; continue; }
    }
    // pro 등 thinking 필수 모델은 thinkingBudget:0을 400으로 거부 → 떼고 재시도
    if (res.status === 400 && !strippedThinking && payload.generationConfig.thinkingConfig) {
      strippedThinking = true;
      delete payload.generationConfig.thinkingConfig;
      continue;
    }
    return json({ error: "llm_error", status: res.status, model, detail }, 502);
  }
  return json({ error: "llm_error", detail: "no usable model" }, 502);
}
