# Microsoft Foundry setup

Beyond the Scoreline calls one Foundry model deployment for every agent turn of the crew (analyst, narrator, fact checker), for the recap, and for the simple pipeline's explainer and verifier, always with structured JSON output. The crew reaches it through Microsoft Agent Framework's `OpenAIChatClient(model, api_key, azure_endpoint)` (`bts.insights.crew.agents.make_chat_client`); the simple pipeline through `bts.insights.llm.LLMClient`, implemented by `bts.insights.foundry.FoundryClient`.

## SDK surface (verified 2026-10-19)

Source: Microsoft Learn, *How to use structured outputs with Azure OpenAI in Microsoft Foundry Models* (page dated 2026-08-24), Python pivot.

- Client: the plain `openai` package (3.x installed; the same surface as 2.x), `OpenAI(base_url="https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/", api_key=...)`. `api_key` is either the resource key or an Entra token provider: `get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")`.
- Structured output: `client.responses.parse(model=DEPLOYMENT, input=..., text_format=PydanticModel)` returns the model in `response.output_parsed`. (Chat Completions equivalent: `client.chat.completions.parse(..., response_format=PydanticModel)`.)
- Schema rules enforced by Azure: every field required, `additionalProperties: false`, no `minimum`/`maximum`/`minLength`/`maxLength`. Our model-facing schemas follow that; limits are checked after parsing.
- Timeouts: `client.with_options(timeout=20.0)`; on timeout the SDK raises `APITimeoutError` (subclass of `APIError`). We wrap every `APIError` in `LLMError`.
- `gpt-5-mini` (version 2025-08-07) is in the supported-models list for structured outputs.

We use the Responses API with `instructions=` for the system prompt, `max_output_tokens=2500` (reasoning tokens count against it) and `reasoning={"effort": "minimal"}` on gpt-5 models to keep latency low. The Agent Framework client gets the same values through `OpenAIChatOptions` (`max_tokens`, `reasoning`, `response_format`).

## Provisioning (manual, once)

1. In the Azure portal create a **Microsoft Foundry** resource (or Azure OpenAI resource) in a region that lists `gpt-5-mini`, and a project.
2. Deploy `gpt-5-mini` (Global Standard) with capacity 500 (500 requests and 500,000 tokens per minute). Every crew insight makes several calls (analyst, narrator, fact checker and their tool rounds); at the default capacity of 50 a fast match that fires many moments at once gets 429 rate-limit errors and falls back to templates. Capacity has no fixed cost; tokens are billed as used:

   ```bash
   az cognitiveservices account deployment create -g bts-rg -n bts-foundry-mt2026 --deployment-name gpt-5-mini \
     --model-format OpenAI --model-name gpt-5-mini --model-version 2025-08-07 --sku-name GlobalStandard --sku-capacity 500
   ```
 If the deployment is refused for quota, open the quota request form linked from the deployment page and deploy `gpt-4.1-mini` meanwhile.
3. Copy the resource's Azure OpenAI v1 endpoint (`https://<resource>.openai.azure.com/openai/v1/`) and a key into `.env` (see `.env.example`). Never commit `.env`.
4. Smoke test:

```bash
uv run pytest tests/insights/test_foundry.py -v
```

The round-trip test is skipped unless `BTS_FOUNDRY_ENDPOINT` is set.

## Cost notes

Each key moment costs one analyst turn (shared by all variants) plus a narrator and a fact-checker turn per profile and language variant actually requested, with tool calls as extra turns, plus one recap per variant. A match produces 13 to 22 moments, so a full match in one variant is under 50 calls of ~2k input tokens with `gpt-5-mini`.
