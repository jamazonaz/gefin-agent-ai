# BRAINSTORM: Fabric MCP Integration (Sales Pipeline Assistant)

> Exploratory session to clarify intent and approach before requirements capture

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FABRIC_MCP_INTEGRATION |
| **Date** | 2026-08-11 |
| **Author** | brainstorm-agent |
| **Status** | ✅ Shipped |

---

## Initial Idea

**Raw Input:** "Tenho um MCP que conecta ao Fabric e tem acesso ao modelo semântico e relatório do Power BI. Se eu quiser que o meu chat conheça o modelo semântico e gere relatórios/gráficos e linhagem de dados, como fazer? Endereço do MCP: https://mcp-fabric-dck4.onrender.com/ — anexei um exemplo de cliente Python (`remote_client_example.py`) que chama a tool `execute_dax_query` via `streamablehttp_client` + `ClientSession`."

**Context Gathered:**
- GEFIN Agent é um agente único (single-agent ReAct: Plan → Tools → Reflect) em `backend/app/agent/graph.py`, com loop explícito (não `StateGraph`), LangChain tools (`ALL_TOOLS`), e providers configuráveis (Anthropic/OpenAI/Ollama).
- Padrão de guardrail atual: **catálogo primeiro** — o agente consulta `catalog/metrics.yaml` (`list_metrics`/`get_metric_definition`) antes de gerar SQL; `execute_sql` só aceita `SELECT` contra views whitelisted, validado com `sqlglot`.
- Linhagem hoje (`get_lineage`) é "linhagem de consulta": views usadas + SQL executado — não é lineage ponta-a-ponta de pipeline.
- Frontend é Streamlit + Plotly (`frontend/app.py`), consumindo `chart_spec` gerado pela tool `generate_chart` (bar/line/pie a partir de dados tabulares).
- Stack já é 100% LangChain (`langchain==0.3.14`, `langchain-anthropic`, `bind_tools`), rodando em loop assíncrono (`run_agent` é `async`).
- Nenhuma integração MCP existia no projeto antes desta sessão (`.env`/`.env.example` não tinham nenhuma variável relacionada).

**Investigação técnica feita nesta sessão (com o token que o usuário adicionou a `.env` como `MCP_AUTH_TOKEN`):**
- `session.list_tools()` no servidor MCP remoto (`https://mcp-fabric-dck4.onrender.com/mcp`) retornou **apenas 3 tools**, nenhuma tool de metadata dedicada:
  - `execute_dax_query(dax_code: str)` — roda DAX via `EVALUATE`; inerentemente read-only (DAX não tem INSERT/UPDATE/DELETE).
  - `list_report_pages()` — nomes/ordem das páginas do report.
  - `list_report_visuals()` — contagem de visuais por tipo, por página (estrutural, sem dados nem export).
- Descoberta de schema via `INFO.TABLES()`/`INFO.MEASURES()` (nível de modelo/admin) retornou **erro 400** — permissão do Service Principal não alcança DMVs de admin.
- `INFO.VIEW.TABLES()` / `INFO.VIEW.MEASURES()` / `INFO.VIEW.COLUMNS()` (funções DAX de nível "view", sem exigir permissão de admin) **funcionaram** e retornaram o schema real:
  - **10 tabelas:** Accounts, Industries, Opportunities, Owners, Products, Contacts, Territories, Campaigns, Opportunity Calendar, Opportunity Forecast Adjustment (oculta).
  - **15 medidas** (14 em `Opportunities`, 1 em `Owners`): Revenue Won, Revenue In Pipeline, Revenue Open, Forecast, Forecast %, Forecast by Win/Loss Ratio, Opportunity Count, Opportunity Count In Pipeline, Count of Won, Count of Lost, Close %, Revenue Won Average Deal Size, Rev Goal, + 2 auxiliares ocultas.
  - **11 páginas de report:** Sales Overview, Win/Loss Ratio Overview, Industries Overview, Pipeline Trends, Trend Analytics, Win/Loss Ratio Insights, Days to Close Insights, Sales Discounting Insights, Revenue Source Breakdown, Q&A Query, Template.
  - Esse schema corresponde ao dataset de amostra "Sales & Marketing Sample" da Microsoft (Pipeline de Vendas / CRM), confirmando que **é um domínio diferente** do atual (Contas a Receber).

**Technical Context Observed (for Define):**

| Aspect | Observation | Implication |
|--------|-------------|-------------|
| Likely Location | `backend/app/agent/` (novas tools + prompts), `backend/app/catalog/` (novo loader ou extensão), `catalog/fabric_metrics.yaml` (novo), `frontend/app.py` (seletor de assistente) | Segue exatamente a estrutura existente do domínio AR, espelhando o padrão catálogo→tools→prompt→frontend |
| Relevant KB Domains | `microsoft-fabric` (semantic-link, power-bi-api patterns), `genai` (tool-calling, agentic-workflow, chatbot-architecture), `python` (async patterns) | KB de `microsoft-fabric` cobre padrões de API/SDK do Fabric; `genai` cobre tool-calling e arquitetura de chatbot multi-domínio |
| IaC Patterns | Docker Compose local + `render.yaml` para deploy | Novas env vars (`MCP_SERVER_URL`, `MCP_AUTH_TOKEN`) precisam ser propagadas também no `render.yaml` do backend, não só local |

---

## Discovery Questions & Answers

| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | O modelo semântico do Fabric é sobre o mesmo domínio (AR) ou um domínio diferente? | **Domínio diferente** | Não é uma fonte alternativa para as mesmas perguntas — é um catálogo/assistente novo e paralelo, não uma fusão de dados |
| 2 | Quais tools o MCP expõe além de `execute_dax_query`? | **Investigamos ao vivo** — só 3 tools (`execute_dax_query`, `list_report_pages`, `list_report_visuals`), sem tool de metadata dedicada | Schema precisa ser descoberto via DAX (`INFO.VIEW.*`) e materializado num catálogo local, não consultado sob demanda a cada pergunta |
| 3 | O entendimento de "linhagem de consulta" (medidas/tabelas usadas + página do report relacionada) em vez de lineage ponta-a-ponta (Purview) está correto? | **Sim, confirmado** — com desejo futuro de lineage mais completa via Purview no roadmap | `get_fabric_lineage` mantém o mesmo formato de resposta do `get_lineage` atual, mas com fonte = "Fabric/Power BI Semantic Model" |
| 4 | Como o agente decide se uma pergunta é de AR ou do domínio Fabric? | **Seleção explícita do usuário** ao abrir um novo chat (como escolher um "plugin"), não triagem automática numa mesma sessão | `/chat` recebe um campo de domínio; cada sessão carrega só o toolset do domínio escolhido; sem necessidade de triagem cross-domain |
| 5 | Descobrir o schema real agora via MCP, ou usar lista já documentada? | **Rodar agora via MCP** (feito nesta sessão) | Catálogo novo (`fabric_metrics.yaml`) pode ser ancorado em dado real, não hipotético |
| 6 | Qual abordagem de integração MCP↔LangChain? | **`langchain-mcp-adapters`**, sessão MCP aberta uma vez por turno de chat (não por tool call) | Define a Approach A como caminho de implementação; evita reescrever schemas de tool à mão |

**Minimum Questions:** 3 ✅ (6 perguntas feitas)

---

## Sample Data Inventory

| Type | Location | Count | Notes |
|------|----------|-------|-------|
| Schema real (tabelas) | Descoberto via `EVALUATE INFO.VIEW.TABLES()` nesta sessão | 10 tabelas | Accounts, Opportunities, Owners, Products, Contacts, Territories, Industries, Campaigns, Opportunity Calendar, Opportunity Forecast Adjustment |
| Schema real (medidas) | Descoberto via `EVALUATE INFO.VIEW.MEASURES()` nesta sessão | 15 medidas | Todas com `[Table]`, `[DataType]`, `[IsHidden]` — prontas para virar entradas do catálogo, no mesmo formato de `catalog/metrics.yaml` |
| Report pages/visuals | `list_report_pages()` / `list_report_visuals()` (tools MCP reais) | 11 páginas | Usado para popular o mapeamento aproximado medida→página no `get_fabric_lineage` |
| Exemplo de cliente MCP | `remote_client_example.py` (anexado pelo usuário) | 1 arquivo | Referência de conexão (`streamablehttp_client` + `ClientSession`), não será importado diretamente — servirá de base para a integração via `langchain-mcp-adapters` |
| Padrão de catálogo existente | `catalog/metrics.yaml` + `backend/app/catalog/loader.py` | 1 domínio (AR) | Estrutura a replicar para `fabric_metrics.yaml` (metrics/dimensions/views → measures/tables) |

**How samples will be used:**

- Schema real (tabelas/medidas) vira o conteúdo inicial de `catalog/fabric_metrics.yaml`, com descrições e exemplos de pergunta por medida (ex: "Qual o Revenue Won por indústria?", "Como está o Win/Loss Ratio?").
- Páginas do report viram uma seção `report_pages` no catálogo, usada por `get_fabric_lineage` para indicar onde a medida aparece hoje no Power BI (quando mapeável).
- `remote_client_example.py` vira referência de teste manual/smoke-test durante o Build, mas a implementação real usa `langchain-mcp-adapters` em vez do `ClientSession` cru.

---

## Approaches Explored

### Approach A: `langchain-mcp-adapters` + sessão MCP por turno de chat ⭐ Recommended

**Description:** Adiciona a dependência `langchain-mcp-adapters` ao backend. Quando a sessão do chat é do domínio Fabric, `run_agent()` abre `streamablehttp_client` + `ClientSession` uma vez por turno (não por tool call), usa `load_mcp_tools(session)` para converter as 3 tools do MCP em tools LangChain automaticamente, combina com tools locais novas (`list_fabric_measures`, `get_fabric_measure_definition`, `get_fabric_lineage`) que seguem o padrão catálogo-primeiro já existente, e reutiliza o loop ReAct existente sem alterar sua lógica central.

**Pros:**
- Schema das tools MCP sempre fiel ao servidor real — sem duplicar JSON schema à mão, sem risco de desalinhamento se o servidor mudar.
- Reaproveita 100% do `graph.py` (loop, `tools_by_name`, dispatch, tratamento de erro, steps) e do padrão de prompts existente.
- Menos código de glue manual — a lib já resolve a conversão MCP→LangChain tool.

**Cons:**
- Uma dependência nova no `requirements.txt`, com possível necessidade de validar compatibilidade de versão com `mcp==1.29.0` e `langchain-core==0.3.29` no Build.
- Ainda é necessário decidir explicitamente (allowlist) quais tools do MCP ficam expostas ao LLM, para não herdar cegamente qualquer tool que o servidor passe a oferecer no futuro.

**Why Recommended:** Stack já é 100% LangChain (`bind_tools`, `ALL_TOOLS`, `langchain-anthropic`) — a lib de adapters é o caminho padrão do ecossistema para isso, com evidência de KB (domínio `genai`/tool-calling) e match direto com a stack existente. Confiança 0.85 (padrão de KB, sem precedente ainda neste código, mas adaptação direta).

---

### Approach B: Tools MCP escritas à mão (sem lib de adapters)

**Description:** 3 funções `@tool` manuais em `backend/app/agent/fabric_tools.py`, cada uma abrindo sua própria conexão MCP curta por chamada (replica exatamente `remote_client_example.py`: um `async with streamablehttp_client(...)` + `ClientSession` por tool call).

**Pros:**
- Zero dependência nova além do pacote `mcp` já usado no script de exemplo.
- Extremamente explícito e fácil de explicar em review de portfólio — sem "mágica" de biblioteca externa.

**Cons:**
- Um turno do ReAct pode chamar várias tools (até `MAX_STEPS=6`); reabrir handshake MCP (TLS + `initialize()`) a cada chamada, contra um servidor Render (sujeito a cold start em planos free/hobby), soma latência real e perceptível ao usuário.
- Schemas de tool duplicados à mão (JSON schema → assinatura Python), tendência a desalinhar se o servidor MCP evoluir.

**Why not recommended:** O custo de latência composto no loop multi-step é o problema central para este caso de uso — a maioria das perguntas provavelmente precisa de 2+ chamadas (catálogo → `execute_dax_query` → `get_fabric_lineage`), e reabrir conexão a cada uma penaliza exatamente o fluxo mais comum.

---

## Data Engineering Context

### Source Systems
| Source | Type | Volume Estimate | Current Freshness |
|--------|------|-----------------|--------------------|
| PostgreSQL (views semânticas de AR) | Banco relacional local/Neon | Dataset de portfólio (baixo volume) | Snapshot diário (`vw_ar_kpi_daily`) |
| Fabric Semantic Model (via MCP) | Power BI/Fabric semantic model (Import mode) | Dataset de amostra "Sales & Marketing Sample" | Import — atualização depende do refresh do modelo no Fabric, fora do controle do GEFIN Agent |

### Data Flow Sketch
```text
[Usuário escolhe assistente: AR | Fabric]
        │
        ├── AR  → Streamlit → FastAPI/Agent → Postgres (views whitelisted) → chart/lineage
        │
        └── Fabric → Streamlit → FastAPI/Agent → MCP (streamablehttp) → Fabric Semantic Model (DAX)
                                                        │
                                            catalog/fabric_metrics.yaml (schema estático,
                                            gerado via INFO.VIEW.* nesta sessão)
```

### Key Data Questions Explored
| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | O MCP permite descoberta de schema sob demanda? | Não há tool dedicada; só via DAX `INFO.VIEW.*` | Catálogo precisa ser materializado (estático), não descoberto a cada pergunta |
| 2 | O acesso é read-only? | Sim — DAX/`EVALUATE` não tem operações de escrita | Reduz a necessidade de um guardrail tipo `sqlglot`; ainda assim, vale restringir a tabelas/medidas do catálogo conhecido |
| 3 | Quem consome a saída? | Mesmo usuário financeiro/analista, agora podendo escolher entre 2 assistentes | Frontend precisa de um seletor de domínio, não dois apps separados |

---

## Selected Approach

| Attribute | Value |
|-----------|-------|
| **Chosen** | Approach A — `langchain-mcp-adapters`, sessão MCP por turno de chat |
| **User Confirmation** | 2026-08-11, nesta sessão |
| **Reasoning** | Stack já 100% LangChain; evita reescrever schemas de tool à mão; evita latência composta de reabrir conexão MCP por tool call dentro do loop multi-step |

---

## Key Decisions Made

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|----------------------|
| 1 | Fabric é um domínio novo e paralelo (não substitui/mistura com AR) | Confirmado pelo usuário; schema descoberto (Sales Pipeline/CRM) não tem relação com Contas a Receber | Fundir os dois domínios numa única resposta |
| 2 | Seleção de domínio explícita pelo usuário ao abrir novo chat | Simplifica guardrails (cada sessão carrega só um toolset); evita o LLM confundir fontes de dados | Triagem automática cross-domain via `triage_scope` estendido |
| 3 | Catálogo estático (`catalog/fabric_metrics.yaml`) em vez de descoberta de schema em tempo real | `INFO.VIEW.*` via DAX é a única forma de metadata disponível; rodar isso a cada pergunta seria lento e redundante | Chamar `INFO.VIEW.TABLES()`/`MEASURES()` a cada turno do agente |
| 4 | Linhagem = medidas/tabelas usadas no DAX + página do report relacionada (quando mapeável) | MCP não expõe lineage ponta-a-ponta (tipo Purview); mantém consistência com o `get_lineage` atual | Prometer lineage completa de pipeline de dados |
| 5 | Integração via `langchain-mcp-adapters`, sessão aberta 1x por turno | Evita latência de reabrir handshake MCP por tool call; reduz código de glue manual | Tools escritas à mão com conexão por chamada (Approach B) |

---

## Features Removed (YAGNI)

| Feature Suggested | Reason Removed | Can Add Later? |
|--------------------|-----------------|-----------------|
| Embutir o relatório Power BI real (visual embedding) | O MCP não retorna embed token nem definição visual, só contagem de visuais por tipo — implementar exigiria Power BI Embedded SDK, integração de auth totalmente diferente | Yes |
| Lineage ponta-a-ponta (estilo Purview) | MCP não expõe essa informação; foco do MVP é lineage de consulta (medidas/tabelas + página do report) | Yes — via integração futura com Purview/Fabric lineage API |
| Descoberta de schema em tempo real a cada pergunta | `INFO.VIEW.*` via DAX a cada turno seria lento e redundante; catálogo estático resolve com o mesmo padrão já usado no domínio AR | Yes — via script de refresh do catálogo, não por pergunta |
| Roteamento automático multi-domínio numa mesma sessão | Usuário já confirmou preferência por seleção explícita ("como escolher um plugin") | Yes — se o produto crescer para precisar disso |
| Escrita/alteração de dados no Fabric | DAX/`EVALUATE` é inerentemente read-only; não há caminho de escrita no MCP | No (bloqueado pela própria natureza do DAX) |

---

## Incremental Validations

| Section | Presented | User Feedback | Adjusted? |
|---------|-----------|----------------|-----------|
| Superfície real do MCP (3 tools, sem metadata dedicada) + implicação no desenho do catálogo | ✅ | Confirmado | Não |
| Definição de "linhagem de consulta" vs. lineage ponta-a-ponta (Purview) | ✅ | Confirmado, com nota de roadmap para Purview futuro | Não |
| Approach A vs. B de integração MCP↔LangChain | ✅ | Approach A confirmada | Não |
| Cortes de escopo (YAGNI) | ✅ | Todos os cortes confirmados | Não |

**Minimum Validations:** 2 ✅ (4 validações completadas)

---

## Suggested Requirements for /define

### Problem Statement (Draft)
O time financeiro/comercial não tem hoje um jeito de perguntar em linguagem natural sobre o modelo semântico de Pipeline de Vendas do Fabric/Power BI (que hoje só existe como relatório estático), com governança e transparência sobre de onde vieram os números — o GEFIN Agent atual só cobre Contas a Receber via Postgres.

### Target Users (Draft)
| User | Pain Point |
|------|------------|
| Analista comercial/financeiro | Precisa abrir o Power BI, navegar entre 11 páginas de report e entender DAX/medidas pra responder perguntas simples sobre pipeline, forecast e win/loss |
| Usuário do GEFIN Agent (atual) | Quer continuar usando o mesmo chat para uma segunda fonte de dados governada, sem misturar contextos de AR e Vendas |

### Success Criteria (Draft)
- [ ] Usuário consegue escolher entre "Assistente AR" e "Assistente Fabric (Vendas)" ao abrir um novo chat
- [ ] Perguntas sobre medidas do catálogo Fabric (Revenue Won, Forecast, Close %, Win/Loss, etc.) retornam dado real via `execute_dax_query`, não alucinado
- [ ] Toda resposta do assistente Fabric inclui uma seção de linhagem (medidas/tabelas usadas + página do report relacionada, quando mapeável)
- [ ] Gráficos são gerados a partir dos dados retornados (reaproveitando `generate_chart`/Plotly), sem depender de embed real do Power BI
- [ ] `catalog/fabric_metrics.yaml` cobre as 15 medidas e 10 tabelas descobertas nesta sessão, com pelo menos 1 exemplo de pergunta por medida

### Constraints Identified
- MCP expõe só 3 tools (`execute_dax_query`, `list_report_pages`, `list_report_visuals`) — nenhuma tool de metadata dedicada.
- Descoberta de metadata via DAX exige `INFO.VIEW.*` (nível "view"); `INFO.TABLES()`/`INFO.MEASURES()` (nível admin) retornam erro 400 com as permissões atuais do Service Principal.
- Servidor MCP hospedado no Render (plano não confirmado — validar cold start/timeout no Build).
- `MCP_AUTH_TOKEN` já adicionado a `.env` local pelo usuário; falta adicionar `MCP_SERVER_URL` e propagar ambas as variáveis para `render.yaml` (deploy).
- Acesso é inerentemente read-only (DAX/`EVALUATE`), reduzindo (mas não eliminando) a necessidade de guardrail tipo `sqlglot`.

### Out of Scope (Confirmed)
- Embedding real de visuais/relatório do Power BI no frontend.
- Lineage ponta-a-ponta (Purview) — fica como item de roadmap futuro.
- Descoberta de schema em tempo real a cada pergunta do usuário.
- Roteamento automático entre domínios AR e Fabric numa mesma sessão.
- Qualquer operação de escrita no Fabric/Power BI.

---

## Session Summary

| Metric | Value |
|--------|-------|
| Questions Asked | 6 |
| Approaches Explored | 2 |
| Features Removed (YAGNI) | 5 |
| Validations Completed | 4 |
| Duration | ~1 sessão (com investigação técnica ao vivo via MCP) |

---

## Next Step

**Ready for:** `/define .claude/sdd/features/BRAINSTORM_FABRIC_MCP_INTEGRATION.md`
