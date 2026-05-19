# Clinic Connect — AI Service Structure Reference

The AI service is split across three services. The **api-gateway** owns the HTTP surface and intent classification. The **prompt-execution-service (PES)** owns the ADK agent runtime. **mongodb-service** holds all state. The gateway and PES are deliberately decoupled — neither knows how the other is implemented. The only shared code between them is `shared-interfaces`.

---

## What is ADK?

ADK stands for **Agent Development Kit** — Google's open-source framework for building multi-agent AI systems, released at Google Cloud NEXT in April 2025. The package is `@google/adk` (TypeScript), available via npm. It is the same framework powering Google's own products including Agentspace and Customer Engagement Suite.

ADK's core model is a **typed class hierarchy for building agent trees**. You define agents as TypeScript classes, compose them into a hierarchy, and the framework manages session state, tool call lifecycles, context, and event streaming through the tree. Agent development feels like writing normal software — classes, inheritance, explicit execution paths — rather than configuring a pipeline in YAML or chaining prompts together.

The primitive types it provides:

- **`SequentialAgent`** — runs child agents one after another, passing session state between them


- **`LlmAgent`** — calls an LLM, can invoke tools, produces structured or free-form output


- **`ParallelAgent`** — runs child agents concurrently


- **`LoopAgent`** — repeats until a condition is met


- **`BaseAgent`** — raw base class for fully custom logic with no LLM involvement



Clinic Connect uses `SequentialAgent` as the root, `LlmAgent` for the router and assistant, and two custom `BaseAgent` subclasses for the worker dispatcher and booking state machine.

---

## Folder Structure

```
api-gateway/src/routes/clinicconnect/
│
├── handlers.ts                  ← HTTP entry point
├── index.ts                     ← Express router mount
│
├── orchestration/               ← pre- and post-LLM pipeline
│   ├── promptInjectionProtection
│   ├── intentClassifier
│   ├── llmOrchestrator          ← dispatches request to PES
│   ├── safetyFilter             ← post-LLM output gate
│   ├── patientDataChunkIndexer  ← writes RAG chunks to DB
│   └── embedder
│
├── prompts/
│   └── systemPrompts            ← intent-specific system prompts
│
└── escalation/                  ← care team / on-call routing
```

```
services/prompt-execution-service/src/
│
└── clinicconnect-adk/           ← the entire ADK agent tree lives here
    │
    ├── agentFactory.ts          ← assembles the full agent tree
    ├── runner.ts                ← executes the tree; manages booking state I/O
    │
    ├── routerAgent.ts           ← decides which sub-agent runs this turn
    ├── workerAgent.ts           ← dispatches to exactly one child based on router output
    ├── assistantAgent.ts        ← read-only LLM agent with tools
    └── bookingAgent.ts          ← deterministic slot-fill state machine (no LLM)
    │
    ├── patientRagTool.ts        ← vector search tool (DB)
    ├── structuredPatientTools.ts ← labs / meds / appointments / wallet tools
    ├── faqSearch.ts             ← FAQ search tool
    ├── prefetchContext.ts       ← data fetchers called by tools
    │
    ├── appointmentBookingInline.ts  ← booking slot-fill logic
    ├── appointmentActionInline.ts   ← book / cancel / reschedule action handler
    │
    ├── routeTypes.ts            ← routing constants, shortcut decision logic
    ├── orchestratedAdkRequest.ts ← shapes the incoming request for the agent
    │
    └── adk*.ts                  ← ADK config, model resolution, trace logging
```

```
services/mongodb-service/src/collections/clinicconnect/
│
└── handlers/
    ├── conversation.create/read/update/query  ← booking state lives here
    ├── message.create/query                   ← chat history
    └── patientDataChunks.upsert/vectorSearch/delete  ← RAG index
```

```
shared-interfaces/src/
└── clinicconnect.ts             ← request/response types shared between services
```

---

## What Each Folder Holds

**`api-gateway/.../clinicconnect/`** — everything the patient HTTP request touches before it leaves the gateway. Auth, injection checks, intent classification, and dispatch to PES. The `orchestration/` subfolder is the pre- and post-LLM pipeline. `systemPrompts.ts` provides the intent-specific system prompt that travels with the request payload to PES.

**`clinicconnect-adk/`** — the complete ADK agent implementation, self-contained inside PES. This folder is the AI service. It holds the agent classes, all tools, the data fetchers those tools call, the booking state machine, and all ADK configuration. Nothing outside this folder needs to know how ADK works. Adding a new tool means adding a file here and registering it in `assistantAgent.ts`.

**`mongodb-service/.../clinicconnect/`** — state storage. The agent is stateless per-turn; this is where booking progress and conversation history live between turns. The runner reads from here at the start of each turn and writes back at the end.

**`shared-interfaces/clinicconnect.ts`** — the contract between services. Request/response shapes that both gateway and PES import. If a shape changes, it changes here.

---

## Execution Flow

A patient message travels through four stages.

**1. Gateway receives the request** (`handlers.ts`)
Auth is checked, the message is sanitized and scanned for injection patterns, and intent is classified via a fast Gemini call. The result is a typed intent bucket (`LAB_RESULTS`, `SCHEDULING`, `GENERAL_HEALTH`, etc.) attached to the outgoing payload.

**2. Gateway dispatches to PES** (`llmOrchestrator.ts`)
The gateway sends the raw query, intent classification, system prompt, and conversation metadata to PES. No chart data is included — the agent fetches that itself via tools.

**3. PES executes the agent tree** (`runner.ts` → agent tree)
The runner reads any in-flight booking state from the database, seeds it into the ADK session, builds the agent tree via `agentFactory.ts`, and starts execution. The router runs first — it either short-circuits deterministically (active slot-fill in progress, no action verb in the message) or asks Gemini to classify the turn into one of four routes. The worker reads that route from session state and runs exactly one child. The assistant calls tools to fetch data and answer; the booking agent runs the slot-fill state machine without touching the LLM.

**4. State is persisted and response returns** (`runner.ts` → gateway)
If booking state changed this turn, the runner writes it back to the database before returning. The response goes back to the gateway, which applies the safety filter and returns the final answer to the patient.

---

## Key Boundaries

The gateway and PES are deliberately decoupled. The gateway does not know ADK exists — it sends a request and waits for a response. PES does not know Express exists — it receives a request and writes back. The `shared-interfaces` package is the only shared code between them.

No service holds a direct database connection. The agent's tools (`prefetchContext.ts`) never talk to the database directly — they go through the database service layer. The `clinicconnect-adk/` folder has no hard dependency on anything outside PES. It imports from `shared-interfaces` for types and uses the data fetchers for retrieval, but the agent logic, tools, and state machine are self-contained.

---

## ADK vs. CrewAI

The two frameworks represent fundamentally different models for building multi-agent systems. Understanding the difference matters because it explains several specific design decisions in Clinic Connect.

### How They Differ

ADK thinks in **agent classes and execution trees**. You define a hierarchy of typed objects, the framework runs them, and session state flows between agents through a managed context object. The execution path is explicit in code — you can read it like a class diagram.

CrewAI thinks in **roles, tasks, and crews**. You define agents by job description (role, goal, backstory as natural language), assign discrete tasks to those agents, bundle them into a crew, and kick it off. The framework handles delegation. In hierarchical mode, a manager agent decides what gets assigned to whom — the execution path is more emergent than explicit.

**CrewAI is Python-only.** A community TypeScript port exists (`crewai-ts`) but has minimal adoption and is not production-ready. A CrewAI implementation of Clinic Connect would require rewriting PES in Python or running a Python sidecar — a significant architectural change before writing a single agent.

### What Would Change in the File Structure

The `clinicconnect-adk/` folder would be replaced with something like:

```
clinicconnect-crew/
│
├── crew.ts                      ← defines agents + tasks + Crew, runs kickoff()
│
├── agents/
│   ├── routerAgent.ts           ← Agent({ role, goal, backstory })
│   └── assistantAgent.ts        ← Agent({ role, goal, backstory, tools })
│
├── tasks/
│   ├── classifyIntentTask.ts    ← Task({ description, agent: routerAgent, output_pydantic })
│   └── answerPatientTask.ts     ← Task({ description, agent: assistantAgent, context: [classifyIntentTask] })
│
└── tools/
    ├── patientRagTool.ts        ← class PatientRagTool extends BaseTool
    ├── structuredPatientTools.ts
    └── faqSearchTool.ts
```

Files that disappear: `agentFactory.ts`, `routerAgent.ts` (as a class), `workerAgent.ts`, `routeTypes.ts`, all `adk*.ts` config files. The tools and `prefetchContext.ts` survive largely unchanged, wrapped in CrewAI's `BaseTool` interface instead of ADK's `FunctionTool`.

### The Booking Agent Problem

This is the sharpest structural difference. The current `bookingAgent.ts` is a `BaseAgent` subclass — a pure TypeScript class with zero LLM calls, running a deterministic slot-filling state machine. ADK makes this a first-class citizen: extend `BaseAgent`, implement `runAsyncImpl`, plug it into the tree like any other agent.

CrewAI has no equivalent. Every agent in a crew is an LLM agent. Three workarounds exist, none of them clean:

Wrapping the state machine as a **tool** means the assistant agent calls `handle_booking()` internally. Booking is no longer a peer agent — it becomes invisible to the crew's orchestration, and the routing separation disappears.

Making it an **LLM agent** with a booking specialist role means trusting a model to follow slot-filling instructions exactly. That is precisely the failure mode the current design was built to avoid. LLMs improvise with medical scheduling in ways that are unsafe.

Using **CrewAI Flows** — the framework's event-driven workflow layer — gets closest to the current behavior. The booking state machine runs as a Flow step that the crew triggers. It works, but it is a separate execution model bolted alongside the crew rather than integrated into it.

### Session State

ADK manages session state as a first-class object. State written by the router agent in turn N is automatically available to the worker agent in the same turn, and the runner seeds it from the database at the start of each new turn. The framework owns the handoff.

CrewAI passes context between tasks explicitly via each task's `context` parameter. State persistence between turns is entirely the developer's responsibility — you read from the database, thread context into each task manually, and write back at the end. The plumbing that ADK handles automatically becomes application code.

### Summary

|   | ADK (current) | CrewAI |
| --- | --- | --- |
| **Language** | TypeScript | Python only |
| **Agent definition** | Typed class hierarchy | Role + task configuration |
| **Routing** | Explicit, code-defined | Emergent, framework-managed |
| **Deterministic agents** | `BaseAgent` subclass, first-class | Not supported natively |
| **Booking state machine** | Clean `BaseAgent`, zero LLM | Tool wrapper, LLM agent, or Flows workaround |
| **Session state** | Framework-managed between agents | Manual threading between tasks |
| **GCP / Gemini integration** | Native | Functional, not optimized |
| **Built-in observability** | Trace + dev UI included | Basic (enterprise platform is paid) |

For Clinic Connect, the decisive factor is the booking agent. The design requires a deterministic, LLM-free execution path for appointment actions. ADK's `BaseAgent` supports that directly. CrewAI does not.