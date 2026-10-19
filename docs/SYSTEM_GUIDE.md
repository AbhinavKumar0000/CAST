# AgroLLaMA: System Guide (Admin / Engineering Edition)

**Audience:** engineers, maintainers and administrators who need to *understand, run, and
extend* the AgroLLaMA system. No prior MCP knowledge is assumed: everything is built up from
first principles.

**Scope:** the *running product*, the MCP tool server plus the FastAPI + LLM orchestration
layer. (The experimental evaluation of the model is documented separately in
`docs/EVALUATION_AND_FIGURES.md`.)

---

## 1. What AgroLLaMA is, in one minute

AgroLLaMA is a **crop-advisory system for Madhya Pradesh (MP), India**. You give it a
latitude and a longitude and it answers: *"Which crops should be grown at this location, right
now, and why?"*

It answers with **real data** rather than the language model's memory. To do that it is split
into two cooperating pieces:

1. **Six deterministic "tools"** that each measure one thing about a location (weather,
   climate, season, risk, soil, crop ranking). These are wrapped as an **MCP server**.
2. **An LLM orchestrator** that decides which tools to call, feeds their outputs back into a
   language model, and lets the model write the final recommendation.

The key engineering idea: **the numbers come from code, not from the model.** The model only
*chooses tools* and *phrases the answer*. This makes the advice reproducible and auditable.

```
 Farmer / UI / API client
          │  POST /analyze {latitude, longitude}
          ▼
 ┌─────────────────────────────┐        MCP (streamable-http)
 │  FastAPI orchestrator        │  POST http://127.0.0.1:8001/mcp
 │  app/main.py                 │ ───────────────────────────────┐
 │  app/orchestrator.py         │                                 ▼
 │  app/llm/gemini_client.py    │        ┌──────────────────────────────────────┐
 │  (LLM = Gemini 2.0 Flash)    │        │  FastMCP server  mcp_server/server.py  │
 └─────────────────────────────┘        │  weather_tool  climate_tool  season_tool│
          ▲   final message +            │  risk_tool     get_soil_by_coordinates  │
          │   tool outputs               │  crop_score                             │
          └──────────────────────────────└──────────────────────────────────────┘
                                                       │
                        Open-Meteo forecast/archive ───┤
                        data/processed/*.geojson|json ─┤
                        crop_log.csv ──────────────────┘
```

---

## 2. From scratch: what is "MCP" and why tools?

**The problem.** A raw LLM knows nothing about today's weather at coordinate 23.25°N, 77.41°E.
If you just ask it, it will invent a plausible-sounding answer (a *hallucination*).

**The classic fix: function/tool calling.** You tell the model "here are some functions you may
call; when you want one, emit a structured call, and I will run it and give you the result."
The model then loops: call → receive result → call again → write a final answer.

**What MCP adds.** The *Model Context Protocol* is a small open standard that standardises how
such tools are **described and invoked over a network**, so any compatible client (Claude
Desktop, Cursor, our own orchestrator) can discover and use the same tools without bespoke
glue code. FastMCP is the Python library that turns ordinary Python functions into MCP tools.

Concretely, MCP defines three verbs this system uses:

| Operation | Meaning |
|---|---|
| `list_tools()` | "What tools exist and what arguments do they take?" → returns names + JSON-schemas. |
| `call_tool(name, args)` | "Run tool `name` with these arguments; give me its result." |
- Transport here is **streamable-http** on `http://<host>:8001/mcp`.

**Why this matters for AgroLLaMA:** the LLM never hard-codes a tool list. At startup the
orchestrator asks the MCP server *"what tools do you have?"*, converts the answers into the
Gemini API's function-declaration format, and hands them to the model. Add a tool to the server
and the LLM can use it, **with no change to the orchestration code**.

---

## 3. Repository map

| Path | What lives here |
|---|---|
| `mcp_server/` | The MCP tool server. One file per tool + `server.py` (registry) + `open_meteo_client.py` (HTTP). |
| `app/` | FastAPI HTTP layer, LLM orchestration, request/response schemas, static web UI. |
| `data/processed/` | `mp_districts.geojson` (district polygons), `soil_fixed.json` (soil table). |
| `crop_log.csv` | Crop registry: per-crop requirements/ranges (the "knowledge base"). |
| `eval/` | Research evaluation harness (protocol, scenarios, metrics, figures). See the eval doc. |
| `scripts/`, `src/`, `notebooks/` | Utility/legacy scratch. `src/index.js` is an unrelated Docker hello-world. |

---

## 4. Runtime architecture (the two processes)

### Process 1: FastMCP server (`mcp_server/server.py`, port 8001)

This is a **standalone, standards-compliant MCP server**. It registers six tools and serves
them over `streamable-http` at `http://<MCP_HOST>:<MCP_PORT>/mcp` (defaults
`127.0.0.1:8001`). Run it directly with:

```powershell
python -m mcp_server.server
```

The functions decorated with `@mcp.tool()` are **thin wrappers**: their name, docstring and
parameter signature *are* the public contract the model sees. All real logic lives in sibling
modules and is called unchanged (`mcp_server/server.py:54-87`).

### Process 2: FastAPI orchestrator (`app/main.py`, port 8000)

This is the HTTP product. It:

1. **Validates configuration on startup**, requires `GEMINI_API_KEY`, the two processed data
   assets, and a loadable soil spatial index (`_startup_health_check`, `app/main.py:137`).
2. **Starts the MCP server as a child process** (`python -m mcp_server.server`) unless
   `MCP_AUTOSTART=false`, then **probes the endpoint** until it responds
   (`app/main.py:191-225`).
3. **Serves** the web UI and API routes.
4. **Terminates the child MCP process cleanly on shutdown** (CTRL_BREAK on Windows, SIGTERM
   elsewhere; `app/main.py:108-130`).

Run it with:

```powershell
uvicorn app.main:app            # UI: http://127.0.0.1:8000/ui
```

### The request path (`POST /analyze`)

```
HTTP body {latitude, longitude}
  → app/main.py: _run_analyze → app.orchestrator.run_analysis
  → GeminiClient.run_tool_calling_loop        (app/llm/gemini_client.py)
       · fetch live tool declarations from the MCP server (list_tools)
       · loop up to 15 rounds: model emits tool calls → dispatch each via MCP call_tool
                               → append results → repeat
       · model emits final text
  → AnalyzeResponse {location, tool_execution_order, tools_output, llm_final_message}
```

The orchestrator is a pure bridge, it adds no logic of its own beyond JSON-safety coercion
(`app/orchestrator.py:41-63`).

### HTTP routes (`app/main.py:266-329`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/`, `/ui` | Serve the browser UI (`app/static/index.html`). |
| GET | `/health` | Liveness + the MCP URL it is using. |
| GET | `/mp-geojson` | District GeoJSON for the map UI. |
| POST | `/analyze`, `/api/analyze` | Run the full analysis. Body: `{"latitude": float, "longitude": float}`. |

---

## 5. The six tools (complete reference)

All tool modules live in `mcp_server/`. Each exposes a `run(...)` that returns a plain `dict`.
Caching keys round lat/lon to **0.1°** so nearby lookups share a cache entry.

### 5.1 `weather_tool`: short-horizon weather  (`weather_tool.py`)

* **Question it answers:** "What is the weather doing here over the next ~week?"
* **Data source:** Open-Meteo **forecast** API; request covers **7 past days + 7 forecast
  days** (`forecast_days=7, past_days=7, timezone=auto`), fields `current` +
  `temperature_2m_max/min`, `precipitation_sum`, `precipitation_probability_max`.
* **Output:** `avg_temp_c`, `min_temp_c`, `max_temp_c`, `total_rainfall_mm` (next 7 d),
  `rainfall_past_7d_mm`, `avg_humidity_percent`, `precipitation_probability_max_7d_percent`,
  `data_period`.
* **Cache:** in-process dict, **TTL 1 hour** (`weather_tool.py:12`).
* **On API failure:** returns the same shape with `null` values plus an `error` string, it
  never raises outside.

### 5.2 `climate_tool`: long-term climate normals  (`climate_tool.py`)

* **Question:** "What is normal here (rainfall/temperature) across the year?"
* **Data source:** Open-Meteo **archive** API, fixed window **2014-01-01 → 2023-12-31**
  (`climate_tool.py:13-14`), daily `temperature_2m_mean` + `precipitation_sum`.
* **Output:** `avg_rainfall_normal_mm` (per-month average), `avg_temp_normal_c`,
  `monthly_avg_temp_c` (months 1–12), `monthly_avg_precip` (mm/month, scaled by 30.44),
  `data_period`.
* **Cache:** **TTL 7 days** (normals barely move).

### 5.3 `season_tool`: the cropping season  (`season_tool.py`)

* **Question:** "Which cropping season are we in, Kharif, Rabi or Zaid?"
* **Logic:** pure calendar in **India Standard Time** via the fixed map
  `MONTH_TO_SEASON` (`season_tool.py:11-24`): Jun–Oct = **Kharif**, Nov–Mar = **Rabi**,
  Apr–May = **Zaid**.
* **Output:** `current_month`, `current_season`. **No network, no cache.**
* **Important:** this identical map is reused by the evaluation harness
  (`eval/scenarios.py` imports it), so season labels are consistent everywhere.

### 5.4 `risk_tool`: drought / heatwave / flood  (`risk_tool.py`)

* **Question:** "How risky is it here right now?"
* **Data:** Open-Meteo **forecast** (30 past days + 7 forecast) **and archive**
  (2019–2023) for a seasonal baseline.
* **Drought (SPI-1).** Computes the observed **30-day rainfall total**, then scores it against a
  **gamma distribution** fitted to the *same calendar month's* monthly totals over 2019–2023
  (zero-inflation handled); converts CDF → z-score via the normal quantile (`_calculate_spi_1`).
  SPI thresholds map to drought probabilities (`risk_tool.py:161-166`). Reported as
  `drought_z_score_30d`.
* **Heatwave.** Counts consecutive days ≥ 35 °C, days ≥ 38 °C, and the 7-day max to assign a
  probability/severity (`_heatwave_probability`).
* **Flood.** Combines 7-day rainfall total, single-day intensity, and antecedent 30-day
  wetness (`_flood_probability`).
* **Output:** `drought_probability`, `flood_probability`, `heatwave_probability`, severities
  for each, `drought_z_score_30d`, climatology mean/std, `precipitation_30d_mm`,
  `precipitation_forecast_7d_mm`.

### 5.5 `get_soil_by_coordinates`: district soil intelligence  (`soil_tool.py`)

* **Question:** "What district is this, and what is the soil like?"
* **Method:** loads `mp_districts.geojson` once with GeoPandas, builds a **spatial index**,
  and does a fast point-in-polygon lookup (`geometry.covers`). District names are **normalised**
  across sources with a small alias table (`east nimar→khandwa`, `west nimar→khargone`,
  `narsimhapur→narsinghpur`; `soil_tool.py:21-25`) and joined to `soil_fixed.json`.
* **Output:** `district`, `dominant_soil`, `soil_characteristics`,
  `agricultural_suitability`.
* **Edge cases:** outside MP → `{"error": "Outside Madhya Pradesh"}`; district present but no
  soil row → empty fields + an explanatory `note` (**never** a silent default).
* **Note:** the tool name is deliberately `get_soil_by_coordinates` (not `soil_tool`) because
  the model is instructed *not* to guess soil; the explicit name reinforces that.

### 5.6 `crop_score`: the deterministic ranker  (`crop_score_tool.py`)

* **Question:** "Given all the above, rank the candidate crops."
* **Input:** a latitude/longitude, **or** an already-fetched evidence bundle
  (`weather`, `climate`, `soil`, `risk`, `season`). If given only coordinates it fetches the
  five other tools itself.
* **Knowledge base:** `crop_log.csv` (21 crops with rainfall range, temperature range, soil,
  seasons, sowing weeks, days-to-harvest, peak-water week, risk sensitivity).
* **Scoring model**, five normalised channels, fixed weights (`crop_score_tool.py:297-304`):

  | Channel | Weight | How it is computed |
  |---|---|---|
  | `rainfall_match` | 0.20 | seasonal rainfall estimate (climate normals for the season's months) vs the crop's rainfall band |
  | `temperature_match` | 0.15 | current temperature vs the crop's temperature band |
  | `soil_type_match` | 0.20 | keyword overlap between crop soil text and dominant soil |
  | `season_alignment` | 0.30 | season supported **and** current ISO week inside the sowing window |
  | `risk_penalty` | 0.15 | risk-sensitivity level × risk probabilities (peak-water weeks ×1.15) |

  Each channel returns 0–1; the weighted sum is the crop's `total_score`.
* **Output:** ranked crops (best first) with per-channel scores; the top-5 is the model's
  evidence. Also reports the current week/season used.
* **Design note:** because ranking depends on district-determined soil and season, scenarios in
  the same district tend to get similar recommendations. This clustering matters statistically
  and is handled explicitly in the evaluation (see the eval doc).

### HTTP client (`open_meteo_client.py`)

Shared `requests.Session` wrapper with **5 retry attempts**, exponential backoff starting at
5 s (doubling), jittered, and typed `OpenMeteoError` on final failure. Two clients: forecast
(timeout 12 s) and archive (timeout 20 s).

---

## 6. End-to-end walkthrough of one `/analyze` call

1. Client POSTs `{"latitude": 23.25, "longitude": 77.41}`.
2. FastAPI runs the pydantic request model, calls `run_analysis`.
3. `GeminiClient.__init__` opens a short-lived MCP session, calls **`list_tools`**, and converts
   the six MCP tool schemas into Gemini **`FunctionDeclaration`s** (stripping fields Gemini
   rejects, see §8).
4. The **tool-calling loop** starts. The system prompt (`gemini_client.py:258`) plus the user
   message (coordinates, today's IST date/week, the crop reference table) are sent to Gemini.
5. Gemini returns one or more **function calls** (e.g. `weather_tool(23.25, 77.41)`).
6. For each call the client opens a fresh MCP session and invokes **`call_tool`**; the server
   runs the real tool and returns structured JSON, which is injected back to Gemini as a
   `FunctionResponse`.
7. Steps 5–6 repeat (up to 15 rounds) until Gemini returns **final text** instead of a call.
8. The response is coerced to native JSON types and returned as `AnalyzeResponse`:
   `tool_execution_order` (the tools Gemini chose, in order), `tools_output` (their results),
   and `llm_final_message`.

---

## 7. Data assets

| Asset | Path | Role |
|---|---|---|
| District polygons | `data/processed/mp_districts.geojson` | 51 MP districts (GADM `NAME_2`); drives soil lookup and maps. |
| Soil table | `data/processed/soil_fixed.json` | Per-district `dominant_soil`, `soil_characteristics`, `agricultural_suitability`. |
| Crop registry | `crop_log.csv` | The 21-crop knowledge base used by `crop_score` and the prompt. |

> **Coverage:** all **51 scenario districts** have soil matches. The only unmatched soil record
> is the orphan "**Niwari**" (a soil row with no polygon and no scenario). Missing metadata is
> reported, never silently defaulted.

---

## 8. Configuration & environment

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | n/a | **Required.** LLM auth for the orchestrator. |
| `MCP_AUTOSTART` | `true` | If false, the app expects an externally-started MCP server. |
| `MCP_SERVER_URL` | `http://127.0.0.1:8001/mcp` | Endpoint the orchestrator talks to. |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8001` | Where the FastMCP server binds. |
| `MCP_PROBE_TIMEOUT` | `30` | Seconds to wait for the MCP endpoint on startup. |

Use `MCP_AUTOSTART=false` when running `uvicorn --reload` (so a new MCP child is not spawned on
every reload) and start the server manually in a second terminal.

---

## 8a. Operations: run, verify, troubleshoot

**Start (single host):**
```powershell
# Terminal 1
python -m mcp_server.server            # MCP on :8001
# Terminal 2
uvicorn app.main:app                    # FastAPI on :8000 (auto-starts MCP unless disabled)
```

**Verify:**
- `GET http://127.0.0.1:8000/health` → `{"status":"ok", "mcp_server":"http://127.0.0.1:8001/mcp"}`.
- `POST http://127.0.0.1:8000/analyze` with a real MP coordinate.

**Common failures:**
| Symptom | Likely cause | Fix |
|---|---|---|
| Startup `GEMINI_API_KEY is missing` | env not set | add to `.env` |
| `MCP server did not become ready` | port 8001 busy / import error / MCP_AUTOSTART mismatch | free the port; run `python -m mcp_server.server` to see the traceback |
| Tool returns `null`s + `error` | Open-Meteo unreachable/rate-limited | retry; the client already backs off 5× |
| `Outside Madhya Pradesh` | coordinate outside MP polygons | expected behaviour |
| Gemini sees no tools / rejects schema | a new tool's schema has unsupported fields | handled by `_strip_gemini_unsupported` (§9) |

---

## 9. Engineering notes & gotchas

* **Gemini schema strictness.** FastMCP auto-generates JSON Schema containing `title`,
  `$schema`, `default`, which Gemini's `FunctionDeclaration` rejects. These are stripped
  recursively (`gemini_client.py:145-161`). Any new tool must survive this stripping.
* **One short-lived MCP session per discover/call.** Tool declarations are fetched once per
  client instance; each tool call opens its own session. Simple and robust; a process-level
  cache is an obvious future optimisation (noted in-code).
* **Type coercion.** Tool outputs can contain NumPy scalars (soil/GeoPandas paths), which are not
  JSON/Proto-safe. `_to_native` / `_to_proto_safe` round-trip everything to primitives
  (`gemini_client.py:43-89`), otherwise the response serialisation 500s.
* **`tools_output` keying.** Results are keyed by the tool's own `"tool"` field (e.g.
  `climate_normals`, `risk_analysis`) with a fallback to the function name.
* **Caching is in-process and per-worker.** Multiple uvicorn workers each hold their own caches;
  weather TTL 1 h, climate 7 d.
* **MCP server is transport-agnostic.** Because it is a plain MCP server, tools are equally
  callable from Claude Desktop, Cursor, or the eval harness, the eval uses the *same* tool code
  via `eval/time_anchored.py` (real tools, injected clock, no live calls).

---

## 10. How to add a new tool (the safe recipe)

1. Create `mcp_server/<name>_tool.py` with a `run(...) -> dict`.
2. Register a thin wrapper in `mcp_server/server.py`:
   ```python
   @mcp.tool()
   def my_tool(latitude: float, longitude: float) -> dict[str, Any]:
       """One-sentence description the model will read."""
       return _my.run(latitude, longitude)
   ```
3. Give it a **clear docstring and simple scalar parameters**, these become the model-visible
   contract. Avoid rich/nested schemas that Gemini might reject.
4. Restart the MCP server. The orchestrator picks it up automatically on the next request via
   `list_tools`, **no change to `gemini_client.py` required**.
5. If the tool needs a data file, add a startup check in `app/main.py:_startup_health_check`.
6. (Optional) To have the evaluation harness exercise it, add it to the condition tool sets in
   `eval/scenarios.py` / `eval/llm/prompts.py`.

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **MCP** | Model Context Protocol, a standard way to expose tools to LLM clients. |
| **FastMCP** | Python library that turns functions into an MCP server. |
| **Tool / function call** | A model emitting a structured request to run a server-side function. |
| **Kharif / Rabi / Zaid** | Monsoon / winter / summer cropping seasons (Jun–Oct / Nov–Mar / Apr–May). |
| **SPI-1** | 1-month Standardised Precipitation Index; a drought z-score. |
| **MCP session** | A live streamable-http connection used to `list_tools` or `call_tool`. |
| **C3** | The deterministic (no-LLM) reference pipeline = the six tools + `crop_score`. |

---

*See also:* `README.md` (project overview) and `docs/EVALUATION_AND_FIGURES.md` (how the system
was evaluated, and the meaning of every result figure). For a deeper treatment, see
`docs/TOOLS_REFERENCE.md` (tool engineering & mathematics), `docs/EVAL_HARNESS_AND_SCENARIOS.md`
(how tools are called and how the experiment is run) and `docs/FIGURES_EXPLAINED.md` (a
figure-by-figure interpretation).
