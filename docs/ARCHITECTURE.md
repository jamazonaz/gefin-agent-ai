# GEFIN Agent — High-Level Architecture (MVP Prototype)

**Status:** Alinhado com a implementação atual (2026-08-06)  
**Objetivo:** Sistema agentic de analytics financeiro (Contas a Receber) em Docker, adequado a portfólio.

**Princípios:**
- Single-agent com loop **Plan → Tools → Observe → Reflect** (ReAct)
- Camada semântica (views) + catálogo leve (YAML)
- Linhagem visível em toda resposta
- LLM configurável: **Claude (padrão)** · OpenAI · Ollama (opcional)
- Sobe com `docker compose up --build`

---

## 1. Diagrama de Contexto (C4 nível 1)

```mermaid
C4Context
    title GEFIN Agent - System Context

    Person(user, "Analista Financeiro", "Time interno")
    System(gefin, "GEFIN Agent", "Chat agentic + analytics governado")
    SystemDb(pg, "PostgreSQL", "Dados de Contas a Receber + views curadas")
    System_Ext(llm, "Claude / OpenAI / Ollama", "LLM")

    Rel(user, gefin, "Pergunta em linguagem natural")
    Rel(gefin, pg, "SQL controlado via tools")
    Rel(gefin, llm, "Reasoning + tool calling")
```

---

## 2. Diagrama de Containers (C4 nível 2)

```mermaid
C4Container
    title GEFIN Agent - Containers (Docker Compose)

    Person(user, "Usuário")

    Container_Boundary(gefin_boundary, "GEFIN Agent") {
        Container(api, "Backend + Chat UI", "FastAPI + Chainlit + LangChain tools", "Orquestração ReAct, tools, memória de sessão, UI de chat montada no mesmo processo (/chainlit)")
        Container(catalog, "Catalog", "YAML montado no backend", "Métricas, definições, exemplos")
        ContainerDb(db, "PostgreSQL 16", "Dados + views semânticas + audit_log")
        Container_Ext(llm, "LLM Provider", "Claude (padrão) / OpenAI / Ollama")
    }

    Rel(user, api, "http://localhost:8000/chainlit (login + chat)")
    Rel(api, catalog, "list_metrics, get_metric_definition")
    Rel(api, db, "execute_sql (whitelisted views only)")
    Rel(api, llm, "Chat + tool calling")
    Rel(api, db, "Escreve audit_log")
```

**Nota:** O serviço `ollama` existe no `docker-compose.yml` com `profiles: [ollama]` — só sobe se você usar `--profile ollama`.

---

## 3. Fluxo Agentic (Sequência)

```mermaid
sequenceDiagram
    participant U as Usuário
    participant CL as Chainlit UI (mesmo processo)
    participant AG as Agent (agent/graph.py, ReAct)
    participant CAT as Catálogo YAML
    participant DB as PostgreSQL
    participant LLM as Claude / OpenAI / Ollama

    U->>CL: Login (usuário/senha único)
    U->>CL: Pergunta em linguagem natural (ou starter)
    CL->>AG: run_agent(msg, session_id, domain, config=callbacks) — chamada direta, sem HTTP

    AG->>LLM: Planeja (system prompt + histórico + tools)
    LLM-->>CL: Tokens da resposta (streaming via cl.LangchainCallbackHandler)

    loop Até ter dados suficientes ou max steps (6)
        alt Precisa de definição de métrica
            AG->>CAT: get_metric_definition / list_metrics
            CAT-->>AG: Definição + view + exemplos
        else Precisa de dados
            AG->>DB: execute_sql (whitelist + LIMIT + sqlglot)
            DB-->>AG: Resultado tabular
            AG->>AG: validate_result()
        else Precisa de gráfico
            AG->>AG: generate_chart()
        end
        AG->>LLM: Observation + próximo passo
    end

    AG->>AG: get_lineage (ou fallback automático)
    AG-->>CL: Resposta + data + chart_spec + lineage + steps
    CL->>DB: INSERT audit_log (write_audit, chamado pelo handler)
    CL-->>U: Texto (streamed) + tabela + gráfico + linhagem + steps do agente
```

---

## 4. Arquitetura Lógica do Agente

```
┌─────────────────────────────────────────────────────────────┐
│                     GEFIN Agent (single)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │   Planner   │→ │  Tool Router │→ │     Reflector      │  │
│  │  (LLM)      │  │              │  │  (LLM + rules)     │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│         │                │                     │            │
│         ▼                ▼                     ▼            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                     Tools                            │   │
│  │  • list_metrics / get_metric_definition              │   │
│  │  • execute_sql (whitelist + sqlglot + LIMIT)         │   │
│  │  • validate_result                                   │   │
│  │  • generate_chart                                    │   │
│  │  • get_lineage                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐     ┌──────────────┐                      │
│  │ Session      │     │ Audit Logger │                      │
│  │ Memory       │     │ (audit_log)  │                      │
│  └──────────────┘     └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**Implementação:** `backend/app/agent/graph.py` (loop ReAct explícito, não StateGraph).

---

## 5. Camada de Dados (MVP)

```
PostgreSQL
├── raw (não exposto ao agente)
│   ├── customers
│   ├── invoices
│   └── payments
│
├── semantic (views whitelisted — ÚNICA camada que o agente enxerga)
│   ├── vw_ar_open_items
│   ├── vw_ar_aging
│   ├── vw_ar_customer_summary
│   ├── vw_ar_kpi_daily
│   └── vw_ar_dso
│
└── system
    └── audit_log
```

**Regra de ouro:** o tool `execute_sql` só aceita `SELECT` contra as views da lista branca (validado com **sqlglot**).

---

## 6. Catálogo Leve

Arquivo: `catalog/metrics.yaml`

Contém métricas, dimensões, views e exemplos de perguntas.  
O agente **deve** consultar o catálogo antes de gerar SQL complexo.

---

## 7. Stack Técnica (implementação atual)

| Camada              | Tecnologia                                      |
|---------------------|-------------------------------------------------|
| Orquestração        | Docker Compose                                  |
| Banco               | PostgreSQL 16                                   |
| Agente              | Python 3.12 + FastAPI + LangChain tools (ReAct) |
| LLM (padrão)        | **Anthropic Claude** (`langchain-anthropic`)    |
| LLM (alternativas)  | OpenAI / Ollama                                 |
| Chat UI             | Chainlit (montado no FastAPI) + Plotly          |
| Catálogo            | YAML + Pydantic-style loader                    |
| Validação SQL       | sqlglot + whitelist de views                    |
| Observabilidade     | Logs estruturados + tabela `audit_log`          |

### Providers de LLM (`LLM_PROVIDER`)

| Valor        | Classe LangChain     | Variáveis necessárias      |
|--------------|----------------------|----------------------------|
| `anthropic`  | `ChatAnthropic`      | `ANTHROPIC_API_KEY`        |
| `openai`     | `ChatOpenAI`         | `OPENAI_API_KEY` (+ base)  |
| `ollama`     | `ChatOllama`         | `OLLAMA_BASE_URL`          |

---

## 8. Estrutura de Pastas (repo)

```
gefin-agent/
├── docker-compose.yml
├── .env.example
├── README.md
├── catalog/
│   └── metrics.yaml
├── db/
│   └── init/
│       ├── 01_schema.sql
│       ├── 02_sample_data.sql
│       └── 03_views.sql
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── chainlit.md            # tela de boas-vindas do Chainlit
│   └── app/
│       ├── main.py            # monta o Chainlit + /health + /catalog
│       ├── chainlit_app.py    # UI de chat (auth, streaming, elementos)
│       ├── agent/
│       │   ├── graph.py      # loop ReAct
│       │   ├── tools.py      # 6 tools + guardrails
│       │   ├── prompts.py
│       │   └── memory.py
│       ├── catalog/loader.py
│       ├── db/connection.py
│       └── audit/logger.py
└── docs/
    ├── ARCHITECTURE.md
    ├── REQUIREMENTS.md
    └── PROTOTYPE_PLAN.md
```

---

## 9. Decisões de Design (portfólio)

1. **Single-agent + tools** em vez de text-to-SQL puro → arquitetura agentic real.
2. **Views + catálogo** → padrão Agentic Data Stack (LLM não vê tabelas brutas).
3. **Linhagem sempre visível** → diferencial de governança.
4. **Claude como padrão** → melhor tool calling; Ollama disponível via profile.
5. **Caminho de evolução claro** → Fase 2: contas a pagar + Iceberg + OpenMetadata.

---

*Documento alinhado com o código em `gefin-agent/` (2026-08-06).*
