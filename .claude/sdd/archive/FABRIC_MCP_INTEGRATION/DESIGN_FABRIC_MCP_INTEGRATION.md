# DESIGN: Fabric MCP Integration (Sales Pipeline Assistant)

> Technical design for implementing Fabric MCP Integration

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FABRIC_MCP_INTEGRATION |
| **Date** | 2026-08-11 |
| **Author** | design-agent |
| **DEFINE** | [DEFINE_FABRIC_MCP_INTEGRATION.md](./DEFINE_FABRIC_MCP_INTEGRATION.md) |
| **Status** | ✅ Shipped |

---

## Architecture Overview

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                          GEFIN Agent — Multi-Domain                        │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Streamlit: seletor "Assistente"] ── domain: ar | fabric                 │
│              │  POST /chat {message, session_id, domain}                  │
│              ▼                                                            │
│      [FastAPI /chat  (main.py)]                                           │
│              │                                                            │
│              ▼                                                            │
│      [run_agent(msg, session_id, domain)]  (graph.py)                     │
│              │                                                            │
│      ┌───────┴────────┐                                                  │
│      ▼                 ▼                                                  │
│  domain="ar"       domain="fabric"                                        │
│      │                 │                                                  │
│      │        ┌────────▼─────────────────────────────┐                   │
│      │        │ fabric_mcp_tools()  (async ctx mgr)   │                   │
│      │        │  1x streamablehttp_client + Session   │──▶ MCP Server     │
│      │        │  per turno de chat                    │   (Render,        │
│      │        │  load_mcp_tools() → allowlist 3 tools │    Streamable     │
│      │        └────────┬─────────────────────────────┘    HTTP)           │
│      │                 │                                       │          │
│      │                 ▼                                       ▼          │
│      │        [+ fabric_tools.py locais:            [Fabric Semantic      │
│      │          list_fabric_measures,                 Model / DAX]        │
│      │          get_fabric_measure_definition,                            │
│      │          get_fabric_lineage,                                       │
│      │          triage_fabric_scope]                                      │
│      │                 │                                                  │
│      ▼                 ▼                                                  │
│  [ALL_TOOLS AR]   [MCP tools + Fabric tools]                              │
│      │                 │                                                  │
│      └────────┬────────┘                                                  │
│                ▼                                                          │
│      [Loop ReAct compartilhado — bind_tools, MAX_STEPS=6]                 │
│                │                                                          │
│      ┌─────────┼──────────────┐                                          │
│      ▼         ▼              ▼                                          │
│ [Postgres] [generate_chart] [get_lineage / get_fabric_lineage]           │
│  (views AR)  (Plotly, reaproveitado)                                     │
│                │                                                          │
│                ▼                                                          │
│      [audit_log (Postgres)] ──▶ [ChatResponse] ──▶ [Streamlit render]    │
│                                                                             │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| Frontend domain selector | Sidebar `selectbox` para escolher "Contas a Receber" ou "Fabric — Pipeline de Vendas"; reseta `session_id` ao trocar | Streamlit |
| FastAPI `/chat` | Recebe `domain` no `ChatRequest`, repassa para `run_agent` | FastAPI + Pydantic |
| Agent Core (`graph.py`) | Loop ReAct, agora com branch por domínio antes do loop (prompt/tools/triage) | LangChain + `asyncio` |
| Fabric MCP Session Manager (`fabric_mcp.py`) | Context manager assíncrono: abre `streamablehttp_client` + `ClientSession` uma vez por turno, converte tools via `load_mcp_tools`, aplica allowlist | `mcp` SDK + `langchain-mcp-adapters` |
| Fabric Tools locais (`fabric_tools.py`) | `list_fabric_measures`, `get_fabric_measure_definition`, `get_fabric_lineage`, `triage_fabric_scope` — mesmo padrão catálogo-primeiro do domínio AR | LangChain `@tool` |
| Fabric Catalog (`fabric_metrics.yaml` + `fabric_loader.py`) | 10 tabelas, 15 medidas, 11 páginas de report descobertas nesta sessão | YAML + `lru_cache` loader |
| Fabric Semantic Model (externo) | Modelo Power BI/Fabric consultado via DAX | Microsoft Fabric, via MCP server no Render |

---

## Key Decisions

### Decision 1: MCP↔LangChain via `langchain-mcp-adapters`, sessão por turno de chat

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-11 |

**Context:** O loop ReAct (`graph.py`) já é assíncrono e usa `bind_tools` do LangChain sobre uma lista estática de tools. Era preciso decidir como conectar as 3 tools do MCP remoto (Render) a esse loop sem reescrever a arquitetura.

**Choice:** Usar `langchain_mcp_adapters.tools.load_mcp_tools(session)` para converter as tools do MCP automaticamente, dentro de um `async with` que abre a sessão MCP uma vez por turno de chat (não por tool call).

**Rationale:** Confirmado (Brainstorm, Approach A) que a stack já é 100% LangChain; a lib evita reescrever schemas de tool à mão e evita reabrir handshake MCP a cada tool call dentro de um turno com até `MAX_STEPS=6`.

**Alternatives Rejected:**
1. Tools MCP escritas à mão, uma conexão por tool call (Approach B do Brainstorm) — rejeitada por latência composta em turnos multi-step.
2. Sessão MCP global, aberta uma vez no startup do FastAPI — rejeitada na Decision 4 abaixo por risco de concorrência.

**Consequences:**
- Uma dependência nova (`langchain-mcp-adapters`) e um bump de versão de `langchain-core` (ver Decision 2).
- Cada turno do domínio Fabric paga 1 handshake MCP, não N.

---

### Decision 2: Bump de `langchain-core` para `0.3.86` (permanece em `<0.4.0`)

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-11 |

**Context:** Ao validar a Decision 1 contra o PyPI real (não assumido), descobri que **toda versão mantida de `langchain-mcp-adapters` (0.1.9+) exige `langchain-core>=0.3.36`**, mas o projeto pina `langchain-core==0.3.29` — uma incompatibilidade real que o DEFINE só registrou como suposição não validada (A-002).

**Choice:** Bump de `langchain-core==0.3.29` → `langchain-core==0.3.86` (a última patch da linha `0.3.x`) e adicionar `langchain-mcp-adapters==0.1.14` (exige `langchain-core>=0.3.36,<2.0.0`, `mcp>=1.9.2`) + `mcp>=1.9.2` explícito no `requirements.txt` (já testado localmente como `mcp==1.29.0` contra o servidor real).

**Rationale:** Verifiquei os metadados PyPI de todos os pacotes LangChain já pinados (`langchain==0.3.14`, `langchain-anthropic==0.3.1`, `langchain-community==0.3.14`, `langchain-ollama==0.2.2`, `langchain-openai==0.2.14`) — todos aceitam `langchain-core<0.4.0` com mínimo entre `0.3.27` e `0.3.29`. O bump para `0.3.86` é um patch dentro da mesma linha, não uma major, e satisfaz simultaneamente todos os pacotes existentes e o requisito do `langchain-mcp-adapters`.

**Alternatives Rejected:**
1. `langchain-mcp-adapters==0.3.2` (mais recente) — exige `langchain-core>=1.0.0`, uma major bump em toda a stack LangChain do projeto; risco de regressão muito maior para o escopo desta feature.
2. Não fazer o bump e cair para Approach B (tools manuais) — rejeitado; o bump dentro da linha `0.3.x` é de baixo risco e evita reabrir a decisão já validada com o usuário.

**Consequences:**
- Build precisa rodar a suite manual de smoke test do domínio AR (não há testes automatizados hoje) após o bump, para garantir que nada quebrou.
- Resolve a assumption A-002 do DEFINE — deixa de ser suposição, vira decisão verificada.

---

### Decision 3: Roteamento de domínio via campo explícito `domain` em `ChatRequest`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-11 |

**Context:** O Brainstorm confirmou que o usuário escolhe o assistente (AR ou Fabric) ao abrir um novo chat, sem triagem automática cross-domain. Era preciso decidir como isso chega ao backend sem duplicar o app FastAPI.

**Choice:** Adicionar `domain: Literal["ar", "fabric"] = "ar"` ao `ChatRequest` (default `"ar"` para compatibilidade retroativa); `run_agent(user_message, session_id, domain)` seleciona `SYSTEM_PROMPT`/`ALL_TOOLS`/`triage_scope` (AR) ou `FABRIC_SYSTEM_PROMPT`/tools do Fabric/`triage_fabric_scope`, e delega para um `_run_react_loop(...)` compartilhado (extraído do corpo atual de `run_agent`) parametrizado por tools/prompts/triage. `memory.py` continua igual — histórico já é escopado por `session_id`.

**Rationale:** Mantém `/chat` como endpoint único (um só contrato para o frontend), `domain="ar"` por padrão preserva o comportamento atual sem quebrar nada, e reaproveita 100% do loop ReAct existente via extração de uma função compartilhada em vez de duplicar o loop.

**Alternatives Rejected:**
1. Endpoint separado `/chat/fabric` — duplicaria o request/response handling e criaria dois contratos para manter sincronizados.
2. Classificador LLM cross-domain reaproveitando `triage_scope` — rejeitado no Brainstorm; usuário quer seleção explícita, não inferência.

**Consequences:**
- `graph.py` precisa de um refactor pequeno: extrair o corpo do loop ReAct (hoje inline em `run_agent`, linhas ~129-253) para `_run_react_loop(user_message, session_id, tools, system_prompt, triage_prompt, triage_tool)`, chamado pelos dois branches.
- Frontend precisa lembrar o domínio selecionado em `st.session_state` e resetá-lo junto com `session_id` no botão "Nova sessão".

---

### Decision 4: Sessão MCP aberta/fechada dentro de `run_agent`, não como singleton do app

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-11 |

**Context:** O backend FastAPI atende usuários concorrentes. Uma `ClientSession` MCP compartilhada no nível do app poderia serializar/misturar conversas não relacionadas, e não há documentação de que `ClientSession` seja segura para chamadas concorrentes intercaladas.

**Choice:** Para turnos do domínio Fabric, abrir `streamablehttp_client(...)` + `ClientSession` dentro de `fabric_mcp_tools()` (chamado de dentro de `run_agent`), inicializar, carregar as tools, rodar o loop ReAct vinculado a elas, e deixar o `async with` fechar a conexão ao fim do turno — mesmo espírito do uso de conexão por request já existente em `db/connection.py` para o Postgres.

**Rationale:** Evita estado mutável compartilhado entre requests concorrentes; aceita o custo de 1 handshake por turno (não por tool call) como trade-off já validado no Brainstorm.

**Alternatives Rejected:**
1. Sessão global mantida no startup do FastAPI — rejeitada: risco de concorrência, complexidade de reconexão em falha, e cold start/idle timeout do Render tornariam uma sessão de longa duração frágil.
2. Sessão por tool call (Approach B) — já rejeitada no Brainstorm por latência.

**Consequences:**
- Todo turno do domínio Fabric paga 1 handshake MCP; um turno com `MAX_STEPS=6` chamando `execute_dax_query` 3 vezes ainda abre a conexão só uma vez.
- Erros de handshake (cold start do Render, ver A-001 do DEFINE) precisam de tratamento explícito de erro, não retry silencioso (ver Error Handling).

---

## File Manifest

| # | File | Action | Purpose | Agent | Dependencies |
|---|------|--------|---------|-------|---------------|
| 1 | `backend/requirements.txt` | Modify | Bump `langchain-core` para `0.3.86`; adicionar `langchain-mcp-adapters==0.1.14` e `mcp>=1.9.2` | (general) | None |
| 2 | `.env.example` | Modify | Documentar `MCP_SERVER_URL`, `MCP_AUTH_TOKEN`, `MCP_TIMEOUT_SECONDS`, `FABRIC_CATALOG_PATH` | (general) | None |
| 3 | `render.yaml` | Modify | Adicionar as mesmas env vars ao serviço `gefin-backend` (`MCP_AUTH_TOKEN` com `sync: false`) | (general) | None |
| 4 | `catalog/fabric_metrics.yaml` | Create | Catálogo com as 10 tabelas, 15 medidas e 11 páginas de report descobertas nesta sessão, com exemplos de pergunta | @fabric-architect | None |
| 5 | `scripts/discover_fabric_schema.py` | Create | Formaliza o script ad hoc usado no Brainstorm (`INFO.VIEW.*` via `execute_dax_query`) como ferramenta reutilizável para atualizar o catálogo quando o modelo mudar | @python-developer | 1 |
| 6 | `backend/app/catalog/fabric_loader.py` | Create | Espelha `catalog/loader.py`: `load_fabric_catalog`, `get_fabric_catalog_summary`, `get_fabric_measure`, `list_fabric_tables`, `get_fabric_report_page` | @python-developer | 4 |
| 7 | `backend/app/agent/fabric_mcp.py` | Create | `fabric_mcp_tools()` — context manager assíncrono com sessão MCP, `load_mcp_tools`, allowlist de tools | @genai-architect | 1 |
| 8 | `backend/app/agent/fabric_tools.py` | Create | Tools locais: `list_fabric_measures`, `get_fabric_measure_definition`, `get_fabric_lineage`, `triage_fabric_scope` | @genai-architect | 6 |
| 9 | `backend/app/agent/prompts.py` | Modify | Adicionar `FABRIC_SYSTEM_PROMPT` e `FABRIC_TRIAGE_SYSTEM_PROMPT` | @genai-architect | 4 |
| 10 | `backend/app/agent/graph.py` | Modify | Extrair `_run_react_loop(...)` compartilhado; `run_agent` ganha parâmetro `domain` e roteia AR vs Fabric (usando `fabric_mcp_tools()`) | @genai-architect | 7, 8, 9 |
| 11 | `backend/app/main.py` | Modify | `ChatRequest.domain: Literal["ar", "fabric"] = "ar"`, repassado a `run_agent` | @python-developer | 10 |
| 12 | `frontend/app.py` | Modify | Sidebar `selectbox` de assistente; reset de `session_id`/mensagens ao trocar domínio; envia `domain` no payload de `/chat` | @python-developer | 11 |
| 13 | `backend/tests/test_fabric_tools.py` | Create | Testes unitários com mocks para `fabric_loader`, `get_fabric_lineage`, `list_fabric_measures` | @test-generator | 6, 7, 8 |

**Total Files:** 13

---

## Agent Assignment Rationale

> Agentes descobertos em `${CLAUDE_PLUGIN_ROOT}/agents/` — o Build invoca os especialistas indicados.

| Agent | Files Assigned | Why This Agent |
|-------|-----------------|------------------|
| @fabric-architect | 4 | Conhecimento de domínio Fabric/Power BI necessário para escrever descrições e exemplos de pergunta corretos por medida/tabela no catálogo |
| @genai-architect | 7, 8, 9, 10 | Integração agentic/tool-calling central — ciclo de vida da sessão MCP, binding de tools, roteamento multi-domínio do loop ReAct |
| @python-developer | 5, 6, 11, 12 | Código Python direto, seguindo convenções já existentes no projeto (`catalog/loader.py`, `main.py`, `frontend/app.py`) |
| @test-generator | 13 | Testes pytest com mocks para as novas tools/catálogo Fabric |
| (general) | 1, 2, 3 | Edições mecânicas de dependências/env vars/deploy config, sem necessidade de especialista |

**Agent Discovery:**
- Escaneado: `${CLAUDE_PLUGIN_ROOT}/agents/**/*.md`
- Match por: tipo de arquivo, palavras-chave de propósito (tool-calling, Fabric, testes), padrões de path (`backend/app/agent/`, `catalog/`)

---

## Code Patterns

### Pattern 1: Sessão MCP por turno + allowlist de tools (`fabric_mcp.py`)

```python
# backend/app/agent/fabric_mcp.py
"""MCP session lifecycle for the Fabric domain — one connection per chat turn."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp-fabric-dck4.onrender.com/mcp")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
MCP_TIMEOUT_SECONDS = int(os.getenv("MCP_TIMEOUT_SECONDS", "60"))

# Allowlist explícita — não confiar cegamente em qualquer tool que o servidor
# passe a expor no futuro (mesma filosofia do whitelist de views em tools.py).
ALLOWED_MCP_TOOLS = {"execute_dax_query", "list_report_pages", "list_report_visuals"}


@asynccontextmanager
async def fabric_mcp_tools() -> AsyncIterator[list[BaseTool]]:
    """Open one MCP session for the current chat turn; yield allow-listed LangChain tools."""
    headers = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"}
    async with streamablehttp_client(
        MCP_SERVER_URL, headers=headers, timeout=MCP_TIMEOUT_SECONDS
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools: list[BaseTool] = await load_mcp_tools(session)
            yield [t for t in tools if t.name in ALLOWED_MCP_TOOLS]
```

### Pattern 2: Roteamento de domínio no loop ReAct (`graph.py`, excerto)

```python
# backend/app/agent/graph.py (excerto — assinatura e branch de domínio)
from app.agent.fabric_mcp import fabric_mcp_tools
from app.agent.fabric_tools import FABRIC_LOCAL_TOOLS, triage_fabric_scope
from app.agent.prompts import FABRIC_SYSTEM_PROMPT, FABRIC_TRIAGE_SYSTEM_PROMPT


async def run_agent(
    user_message: str, session_id: str, domain: str = "ar"
) -> dict[str, Any]:
    """Route to the AR or Fabric toolset, then run the shared ReAct loop."""
    if domain == "fabric":
        async with fabric_mcp_tools() as mcp_tools:
            tools = [*mcp_tools, *FABRIC_LOCAL_TOOLS]
            return await _run_react_loop(
                user_message,
                session_id,
                tools,
                system_prompt=FABRIC_SYSTEM_PROMPT,
                triage_prompt=FABRIC_TRIAGE_SYSTEM_PROMPT,
                triage_tool=triage_fabric_scope,
            )

    return await _run_react_loop(
        user_message,
        session_id,
        ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        triage_prompt=TRIAGE_SYSTEM_PROMPT,
        triage_tool=triage_scope,
    )


async def _run_react_loop(
    user_message: str,
    session_id: str,
    tools: list,
    *,
    system_prompt: str,
    triage_prompt: str,
    triage_tool,
) -> dict[str, Any]:
    """Shared ReAct loop body — extracted from the current run_agent (unchanged logic)."""
    # Corpo atual de run_agent (build/LLM/triagem/loop/steps) migra para cá,
    # substituindo as referências fixas a SYSTEM_PROMPT/ALL_TOOLS/triage_scope
    # pelos parâmetros system_prompt/tools/triage_tool.
    ...
```

### Pattern 3: Estrutura do catálogo Fabric (`catalog/fabric_metrics.yaml`)

```yaml
# catalog/fabric_metrics.yaml
version: "1.0"
domain: sales_pipeline_fabric

measures:
  - id: revenue_won
    name: "Revenue Won"
    description: "Soma da receita de oportunidades fechadas como ganhas."
    table: Opportunities
    dax_reference: "Opportunities[Revenue Won]"
    data_type: Integer
    examples:
      - "Qual o Revenue Won total?"
      - "Revenue Won por indústria"

  - id: close_rate
    name: "Close %"
    description: "Percentual de oportunidades fechadas como ganhas sobre o total."
    table: Opportunities
    dax_reference: "Opportunities[Close %]"
    data_type: Number
    examples:
      - "Qual a taxa de conversão (close rate)?"

  # ... demais 13 medidas descobertas via INFO.VIEW.MEASURES() (ver script #5)

tables:
  - name: Opportunities
    hidden: false
    description: "Tabela central de oportunidades de venda; concentra 14 das 15 medidas."
  - name: Accounts
    hidden: false
    description: "Contas/clientes associados às oportunidades."
  # ... demais 8 tabelas descobertas via INFO.VIEW.TABLES()

report_pages:
  - name: "Sales Overview"
    related_measures: [revenue_won, close_rate]
  - name: "Win/Loss Ratio Overview"
    related_measures: [close_rate]
  # ... demais páginas — mapeamento aproximado, não garantido (ver A-003 do DEFINE)
```

---

## Data Flow

```text
1. Usuário abre novo chat no Streamlit e escolhe o assistente
   ("Contas a Receber" | "Fabric — Pipeline de Vendas")
   │  grava em st.session_state.domain; reseta session_id/mensagens
   ▼
2. Usuário envia pergunta → POST /chat {message, session_id, domain}
   │
   ▼
3. FastAPI valida ChatRequest (Literal["ar","fabric"]) → run_agent(msg, session_id, domain)
   │
   ▼
4. domain == "fabric"?
   ├─ Sim → abre fabric_mcp_tools() (1 handshake MCP) → toolset =
   │        MCP tools allowlisted + tools locais de catálogo/linhagem
   └─ Não → usa ALL_TOOLS existentes (Postgres, inalterado)
   │
   ▼
5. Loop ReAct compartilhado (até MAX_STEPS=6): catálogo → execute_dax_query
   (ou execute_sql) → validação/linhagem → generate_chart (reaproveitado)
   │
   ▼
6. Sessão MCP fecha ao sair do `async with` (fim do turno)
   │
   ▼
7. ChatResponse (answer, data, chart_spec, lineage) → Streamlit renderiza
   com render_chart/render_lineage já existentes (sem mudança de UI de chart)
   │
   ▼
8. audit_log grava a interação (audit/logger.py, schema inalterado)
```

---

## Integration Points

| External System | Integration Type | Authentication |
|------------------|-------------------|------------------|
| Fabric MCP Server (Render) | Streamable HTTP (protocolo MCP) via `langchain-mcp-adapters` | Bearer token (`MCP_AUTH_TOKEN`) |
| Fabric Semantic Model | Indireto — via `execute_dax_query` exposto pelo MCP | Gerenciado pelo MCP server (Service Principal do Fabric, fora do controle do GEFIN Agent) |

---

## Testing Strategy

| Test Type | Scope | Files | Tools | Coverage Goal |
|-----------|-------|-------|-------|----------------|
| Unit | `fabric_loader.py` (catálogo), `get_fabric_lineage`, `list_fabric_measures`, `get_fabric_measure_definition` | `backend/tests/test_fabric_tools.py` | pytest | 80% |
| Integration | `fabric_mcp_tools()` + `load_mcp_tools` contra servidor MCP real (smoke test manual) | `scripts/discover_fabric_schema.py` (reaproveitado) | Execução manual com token real; mock de `ClientSession` para qualquer teste em CI | Cobre AT-001 |
| E2E | Fluxo completo via `/chat` com `domain="fabric"`, incluindo seletor no Streamlit | Manual | - | AT-001, AT-002, AT-003 do DEFINE |

---

## Error Handling

| Error Type | Handling Strategy | Retry? |
|------------|---------------------|--------|
| Handshake/timeout MCP (cold start do Render) | Capturado em `run_agent` (mesmo padrão do `try/except` já existente para falha de LLM call); mensagem clara ao usuário, nunca inventa valor | Não — usuário tenta de novo (ver A-001 do DEFINE) |
| `execute_dax_query` retorna erro (400 permissão, DAX inválido) | Tool retorna `{"error": ...}`, como as tools atuais; LLM decide como comunicar, nunca alucina | Não |
| Medida/tabela fora do catálogo | `get_fabric_measure_definition` retorna `{"error": "Métrica não encontrada"}`, mesmo padrão de `get_metric_definition` | Não |
| `domain` inválido no request | Pydantic `Literal["ar", "fabric"]` rejeita com 422 antes de chegar no agente | Não |

---

## Configuration

| Config Key | Type | Default | Description |
|------------|------|---------|--------------|
| `MCP_SERVER_URL` | string | `https://mcp-fabric-dck4.onrender.com/mcp` | Endpoint do servidor MCP remoto do Fabric |
| `MCP_AUTH_TOKEN` | string | *(obrigatório, sem default)* | Bearer token do MCP — nunca logar |
| `MCP_TIMEOUT_SECONDS` | int | `60` | Timeout da conexão MCP (cobre cold start do Render) |
| `FABRIC_CATALOG_PATH` | string | `/app/catalog/fabric_metrics.yaml` | Caminho do catálogo Fabric, mesmo padrão de `CATALOG_PATH` |

---

## Security Considerations

- `MCP_AUTH_TOKEN` nunca deve ser logado nem incluído em `audit_log` — mesmo tratamento hoje dado a `ANTHROPIC_API_KEY`.
- Tools do MCP são explicitamente allowlisted (`ALLOWED_MCP_TOOLS`) em vez de confiar em tudo que `load_mcp_tools()` retornar, caso o servidor exponha tools novas no futuro sem aviso.
- Tabelas potencialmente sensíveis (`Contacts`) não entram no catálogo/whitelist até confirmação explícita (A-004 do DEFINE); `get_fabric_measure_definition` só retorna medidas do catálogo, nunca colunas brutas de tabela.
- DAX via `execute_dax_query` é inerentemente read-only (`EVALUATE`), reduzindo risco de escrita acidental — mas a allowlist de tools continua necessária como defesa em profundidade.

---

## Observability

| Aspect | Implementation |
|--------|------------------|
| Logging | `logger.info`/`warning` já existentes em `graph.py`, estendidos para incluir `domain` nas mensagens de tool call; `MCP_AUTH_TOKEN` nunca aparece em log |
| Metrics | Nenhuma nova para o MVP; `latency_ms` já retornado por `run_agent` cobre também o domínio Fabric |
| Tracing | `audit_log` (Postgres) grava `tools_called`, `lineage` e `latency_ms` também para o domínio Fabric, sem mudança de schema |

---

## Pipeline Architecture (if applicable)

Não aplicável — esta feature é uma integração de consulta read-only via MCP (schema estático materializado em `catalog/fabric_metrics.yaml`, atualizado sob demanda pelo script #5), não um pipeline de dados. Sem DAG, sem particionamento, sem estratégia incremental.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-11 | design-agent | Versão inicial, a partir de `DEFINE_FABRIC_MCP_INTEGRATION.md` |
| 1.1 | 2026-08-11 | ship-agent | Shipped and archived |

---

## Next Step

**Ready for:** `/ship .claude/sdd/features/DEFINE_FABRIC_MCP_INTEGRATION.md`
