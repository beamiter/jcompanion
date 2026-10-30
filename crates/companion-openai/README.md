# Eva Responses adapter

This is a new, sans-I/O **Responses** adapter, not Chat Completions with a renamed endpoint. The daemon runs an explicitly invoked HTTP worker; render/actor threads never do network I/O. The daemon requires `/usr/bin/curl` with HTTPS support. No shell tools or model-driven execution exist here.

## Explicit configuration

Place `provider.json` in the private daemon profile directory (0600 recommended):

```json
{
  "enabled": false,
  "provider": "openai_responses",
  "endpoint": "https://api.openai.com/v1/responses",
  "model": "REPLACE_WITH_YOUR_CONFIGURED_MODEL",
  "structured_outputs": false,
  "max_output_tokens": 768,
  "timeout_ms": 30000,
  "max_requests_per_session": 32
}
```

There is deliberately no default model. Enable only after choosing a model/capability combination supported by your account. `structured_outputs: false` means literal plain text **without extracted gestures, action suggestions, or memory proposals**, even when the text looks like JSON. No automatic fallback retries or proactive requests are performed. The maximum is one inflight request; cancellation retains the slot until the bounded worker exits. Request count is a session budget, not a monetary estimate.

Credentials belong only to the daemon. The existing Eva environment strategy `OPENAI_API_KEY` is reused; an optional daemon-only `EVA_COMPANION_OPENAI_API_KEY` override is available. Eva Secret Service/file resolution is not silently imported by this transport; deployments using those sources should inject a trusted daemon credential resolver instead of copying keys into GUI config. Eva's existing voice/model selection is not changed. Do not put a key in this config, shell history, frontend configuration, issue, or logs. Curl receives Authorization through stdin rather than process arguments; error output is suppressed and application errors are fixed categories. The endpoint is validated exactly; redirects are disabled; trusted proxy/TLS environment policy is preserved. Both credential variables are removed from the curl child environment. `store:false` is not a promise of zero provider logging or ZDR.

## Privacy and response contract

Inputs contain identity rules, explicit user request, and (only after the daemon's exact host/pane/task/project/revision one-use review) bounded selected evidence with provenance. Memory must be retrieved with current consent through the memory store's paused-aware retrieval API. There is no filesystem, SSH, clipboard, scrollback, or audio collection in this crate. Evidence/memory are untrusted user-role data, never developer instructions.

`text.format` uses strict `json_schema`. Every decision field is mandatory; duplicate members at every depth use jagent's shared validator. Unknown decision fields, invalid gestures/intents/targets, malformed output, refusal, incomplete responses, oversized input/output, 429 and other HTTP failures fail closed. Provider envelope metadata is extensible; only completed assistant text messages (and inert reasoning metadata) are admitted. Model suggestions cannot execute actions, change task success, or persist memory. The UI must independently review proposals.

Ledger states distinguish generated, displayed, actual audibly-played duration and interrupted. A completed text response does not imply speech playback or task completion. The existing Eva owner remains the only voice route.

## Verification / opt-in live smoke

`cargo test -p companion-openai --offline` tests **synthetic frozen fixtures, not live API behavior**. Daemon provider tests use an explicitly labeled mock transport and cover idle zero requests, one inflight, cancellation, deduplication, timeout, 429, budget exhaustion and stale-context display rejection. No test normally reads a real key or sends a request.

A real smoke has **not** been run. To verify a configured model after explicitly authorizing network and its billed usage: use a private test profile, set a small request/output budget, configure the model and capability, provide the daemon-only key securely, launch the daemon, then send exactly one non-sensitive native Companion Card question. Check the origin-bound reply and actual provider usage; test plain and structured modes separately. Do not enable automatically just to run tests. Stop/delete the temporary credential environment afterward. No cost claim or live-capability claim follows from fixtures.

Official protocol references checked for implementation:
- https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
- https://developers.openai.com/api/docs/guides/migrate-to-responses

Native UI, physical audio and live provider capability need separate evidence; offline tests do not certify them.
