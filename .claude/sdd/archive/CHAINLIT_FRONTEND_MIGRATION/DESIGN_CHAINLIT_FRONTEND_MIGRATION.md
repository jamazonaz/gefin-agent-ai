# DESIGN: Chainlit Frontend Migration

> Technical design for replacing the Streamlit frontend with Chainlit, mounted inside the existing FastAPI backend

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | CHAINLIT_FRONTEND_MIGRATION |
| **Date** | 2026-08-12 |
| **Author** | design-agent |
| **DEFINE** | [DEFINE_CHAINLIT_FRONTEND_MIGRATION.md](./DEFINE_CHAINLIT_FRONTEND_MIGRATION.md) |
| **Status** | ✅ Shipped |

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│              GEFIN Agent — Single Service (Render, free tier)          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Browser ──HTTPS──▶ FastAPI app (uvicorn, port 8000, app/main.py)       │
│                        │                                                │
│                        ├─ mount_chainlit() ──▶ Chainlit UI              │
│                        │                        (app/chainlit_app.py)  │
│                        │        @cl.password_auth_callback (login)     │
│                        │        @cl.set_chat_profiles (ar / fabric)    │
│                        │        @cl.set_starters (perguntas-exemplo)   │
│                        │        @cl.on_chat_start (session_id, domain) │
│                        │        @cl.on_message ──▶ run_agent()         │
│                        │              (in-process call, sem HTTP;      │
│                        │               cl.LangchainCallbackHandler     │
│                        │               streama tokens + steps)         │
│                        │                   │                           │
│                        │                   ▼                           │
│                        │         Agent core (app/agent/graph.py)       │
│                        │         contrato run_agent() inalterado       │
│                        │           ┌───────┼────────┐                  │
│                        │           ▼       ▼        ▼                  │
│                        │     PostgreSQL  Fabric MCP  LLM (Claude /     │
│                        │     (views)     (remoto)    OpenAI / Ollama)  │
│                        │                                                │
│                        └─ GET /health, GET /catalog (REST preservadas, │
│                             sem autenticação — não expõem dados)        │
│                                                                          │
│  REMOVIDO: POST /chat como rota REST pública (ver Decisão 4)           │
└────────────────────────────────────────────────────────────────────────┘
```

**Antes → Depois (topologia de deploy):**

| | Antes | Depois |
|---|---|---|
| Serviços em produção | Render (`gefin-backend`, `render.yaml`) + Streamlit Community Cloud (fora do IaC) | 1 único serviço Render (`gefin-backend`), mesmo `render.yaml` |
| Comunicação frontend↔agente | HTTP `POST /chat` | Chamada Python direta a `run_agent()` |
| Autenticação | Nenhuma (app público) | `@cl.password_auth_callback`, login único compartilhado |

---

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| Chainlit UI (`backend/app/chainlit_app.py`) | Login, seleção de domínio, perguntas-exemplo, chat com streaming, renderização de tabela/gráfico/linhagem/steps | Chainlit (ASGI, sobre Starlette) |
| FastAPI app (`backend/app/main.py`) | Monta o Chainlit via `mount_chainlit`; mantém `/health` e `/catalog` | FastAPI (inalterado nesses dois endpoints) |
| Agent core (`backend/app/agent/graph.py`) | Loop ReAct (Plan → Tools → Reflect); passa a aceitar `callbacks` do LangChain para permitir streaming | LangChain (`ChatAnthropic`/`ChatOpenAI`/`ChatOllama`, `.bind_tools().ainvoke()`) |
| Sessão em memória (`backend/app/agent/memory.py`) | Histórico de conversa por `session_id` | dict em memória de processo (inalterado) |
| Deploy | 1 serviço web Docker no Render (free tier) | `render.yaml` + `backend/Dockerfile` |

---

## Key Decisions

### Decision 1: Montar o Chainlit dentro do FastAPI existente via `mount_chainlit`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |

**Context:** O Chainlit não tem um "Community Cloud" gratuito equivalente ao do Streamlit; ele roda como sua própria app ASGI. O backend (`backend/app/main.py`) já expõe `run_agent()` como uma função assíncrona desacoplada, importável de `app.agent.graph`, sem dependência do objeto `Request`/`Response` do FastAPI.

**Choice:** Usar `mount_chainlit(app=app, target="app/chainlit_app.py", path="...")` dentro de `backend/app/main.py`, mantendo o mesmo `app` FastAPI que já serve `/health` e `/catalog`. O handler de mensagens do Chainlit chama `run_agent()` diretamente, em vez de fazer uma requisição HTTP.

**Rationale:** Elimina a viagem de rede entre frontend e backend (pré-condição para streaming real), reduz de 2 para 1 serviço de deploy, e mantém a API REST intacta para os dois endpoints que fazem sentido continuarem públicos.

**Alternatives Rejected:**
1. Chainlit como serviço standalone chamando `/chat` via HTTP — rejeitado no Brainstorm: exigiria SSE/WebSocket entre serviços para streaming, e manteria 2 serviços free-tier (mais cold start).
2. Manter Streamlit e apenas adicionar auth via proxy reverso — rejeitado: Streamlit não tem streaming de resposta nativo comparável ao Chainlit, não resolveria a motivação principal (a).

**Consequences:**
- Acopla o ciclo de vida de deploy do chat UI ao do backend (aceito — projeto de portfólio, mantenedor único).
- `main.py` perde a rota `POST /chat` como endpoint standalone (ver Decisão 4) — comportamento equivalente passa a viver em `chainlit_app.py`.

---

### Decision 2: Streaming e visibilidade de steps via `cl.LangchainCallbackHandler`, sem reescrever o loop ReAct

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |

**Context:** `_run_react_loop` (`backend/app/agent/graph.py:175-409`) já usa LangChain (`llm_with_tools.ainvoke(messages)`) em um loop bounded (`MAX_STEPS`) que intercala chamadas ao LLM e execução de tools. O loop precisa do `AIMessage` completo em cada iteração para decidir se há `tool_calls` — não dá para trocar cegamente todo `.ainvoke()` por `.astream()` sem repensar essa decisão a cada chunk.

**Choice:** Não reescrever o loop. Em vez disso, `chainlit_app.py` cria um `cl.LangchainCallbackHandler` por mensagem recebida e passa `config={"callbacks": [handler]}` para `run_agent()`, que precisa aceitar e repassar esse `config` até as chamadas `.ainvoke()` internas (as duas em `_run_react_loop`, mais a de triagem quando aplicável). O callback handler é a integração nativa do Chainlit com LangChain: ele cria um `cl.Step` por tool call automaticamente e streama os tokens de texto da resposta final para a `cl.Message` do usuário, sem exigir lógica extra de streaming manual.

**Rationale:** Menor superfície de mudança no loop já testado (`_run_react_loop`); reaproveita uma integração first-class do Chainlit em vez de implementar streaming customizado. Resolve as metas MUST (streaming) e SHOULD (steps visíveis) com a mesma mudança.

**Alternatives Rejected:**
1. Reescrever o loop para usar `.astream()` em toda chamada, inspecionando chunks para detectar `tool_call_chunks` — rejeitado: maior risco de regressão no loop existente (detecção de duplicatas, `loop_detected`, limite de steps) para um ganho que o callback handler já entrega.
2. Streaming manual via `msg.stream_token()` chamado a partir de um callback customizado escrito à mão — rejeitado: reimplementa o que `cl.LangchainCallbackHandler` já faz.

**Consequences:**
- `run_agent()` e `_run_react_loop()` ganham um parâmetro opcional `config: RunnableConfig | None = None` repassado às chamadas `.ainvoke()` — mudança pequena e aditiva, não quebra os testes existentes (`backend/tests/test_fabric_tools.py`) que chamam sem esse parâmetro.
- **Risco a validar no Build:** confirmar o nome exato da classe/import (`cl.LangchainCallbackHandler` ou equivalente na versão instalada do Chainlit) e se ela cobre `ChatAnthropic`/`ChatOllama` da mesma forma que `ChatOpenAI` — este KB não tem domínio Chainlit para validar; checar a documentação oficial do pacote instalado antes de codar (ver Assumption A-002/A-004 do DEFINE).

---

### Decision 3: Domínio e perguntas-exemplo via `@cl.set_chat_profiles` e `@cl.set_starters`, não widgets customizados

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |

**Context:** O Streamlit atual usa uma sidebar customizada (`st.selectbox` para domínio `ar`/`fabric`, botões para perguntas-exemplo). Chainlit tem primitivas nativas para os dois casos: `@cl.set_chat_profiles` (perfis selecionáveis antes de iniciar o chat) e `@cl.set_starters` (prompts sugeridos clicáveis na tela inicial).

**Choice:** Mapear os dois domínios (`ar` = "Contas a Receber", `fabric` = "Fabric — Pipeline de Vendas") como `cl.ChatProfile`; mapear as listas `ar_examples`/`fabric_examples` de `frontend/app.py` como `cl.Starter` por perfil.

**Rationale:** Usa componentes nativos em vez de reconstruir UI customizada — menos código, comportamento de UX já validado pelo framework.

**Alternatives Rejected:**
1. Recriar um seletor customizado via `cl.Action`/botões — rejeitado: `set_chat_profiles`/`set_starters` já resolvem exatamente esse caso de uso.

**Consequences:**
- **Risco a validar no Build:** confirmar a API exata (`cl.ChatProfile`, `cl.Starter`) na versão instalada — não validado por KB.

---

### Decision 4: Remover a rota `POST /chat` como endpoint REST público

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |

**Context:** O DEFINE pede autenticação (MUST) e "comportamento equivalente a `/chat`" preservado (não necessariamente a rota REST em si). Se `POST /chat` continuar existindo como endpoint HTTP aberto (hoje sem auth, `CORS allow_origins=["*"]`) depois da fusão, qualquer pessoa pode contornar o login do Chainlit chamando o backend diretamente — reabrindo exatamente o furo de segurança que motivou a troca.

**Choice:** Remover a rota `@app.post("/chat")` de `backend/app/main.py`. O comportamento equivalente passa a existir apenas dentro do handler `@cl.on_message` de `chainlit_app.py`, protegido pela autenticação do Chainlit. `write_audit(...)` (hoje chamado dentro do endpoint `/chat`) move para dentro desse handler.

**Rationale:** É a única forma de a autenticação (meta MUST) ser real e não apenas cosmética. `/health` e `/catalog` continuam públicos porque não expõem dados sensíveis nem executam SQL.

**Alternatives Rejected:**
1. Manter `/chat` público e confiar só na auth do Chainlit para a UI — rejeitado: deixaria um bypass trivial (`curl` direto no backend), inconsistente com o motivo (c) do Brainstorm.
2. Proteger `/chat` com uma segunda camada de auth (ex.: API key) só para essa rota — rejeitado por YAGNI: nenhum consumidor externo de `/chat` foi identificado; complexidade sem necessidade comprovada.

**Consequences:**
- Quebra de compatibilidade para qualquer script/teste que hoje chame `POST /chat` diretamente (nenhum foi encontrado no repositório além do próprio `frontend/app.py`, que está sendo retirado).
- `ChatRequest`/`ChatResponse` (Pydantic models em `main.py`) deixam de ser usados por uma rota HTTP; ficam como referência de contrato interno ou são removidos se não usados em mais lugar nenhum (Build decide, verificando usos).

---

## File Manifest

| # | File | Action | Purpose | Agent | Dependencies |
|---|------|--------|---------|-------|--------------|
| 1 | `backend/app/chainlit_app.py` | Create | UI Chainlit: auth callback, chat profiles (ar/fabric), starters, `on_chat_start` (gera `session_id`), `on_message` (chama `run_agent`, streaming via callback, renderiza dataframe/gráfico/linhagem/steps), `write_audit` | @python-developer | None |
| 2 | `backend/app/main.py` | Modify | Monta o Chainlit (`mount_chainlit`); remove a rota `POST /chat`; mantém `/health`, `/catalog` | @python-developer | 1 |
| 3 | `backend/app/agent/graph.py` | Modify | `run_agent()` e `_run_react_loop()` aceitam `config: RunnableConfig \| None` opcional, repassado às chamadas `.ainvoke()` (incluindo a de triagem) | @python-developer | None |
| 4 | `backend/requirements.txt` | Modify | Adiciona `chainlit` (versão fixada) | (general) | None |
| 5 | `backend/Dockerfile` | Modify | Sem mudança de `COPY` (já copia `backend/app` inteiro); revisar `CMD` se o Chainlit exigir algo além de `uvicorn app.main:app` | (general) | 1 |
| 6 | `chainlit.md` | Create | Tela de boas-vindas do Chainlit — substitui o texto "Sobre" da sidebar atual | (general) | None |
| 7 | `render.yaml` | Modify | Adiciona `CHAINLIT_AUTH_SECRET`, `APP_USERNAME`, `APP_PASSWORD` (todos `sync: false`) ao serviço único `gefin-backend` existente | (general) | 2 |
| 8 | `docker-compose.yml` | Modify | Remove o serviço `frontend` inteiro; adiciona `CHAINLIT_AUTH_SECRET`/`APP_USERNAME`/`APP_PASSWORD` às variáveis do serviço `backend` (via `.env`) | (general) | 2 |
| 9 | `frontend/app.py`, `frontend/Dockerfile`, `frontend/requirements.txt`, `frontend/constraints-docker.txt` | Delete | Retira o frontend Streamlit, substituído por `backend/app/chainlit_app.py` | (general) | 1, 2, 3 |
| 10 | `backend/tests/test_chainlit_app.py` | Create | Cobre AT-001 a AT-004: auth callback aceita/rejeita credenciais, `chat_profile` mapeia para `domain` correto, `/health`/`/catalog` respondem após o mount, `run_agent` é chamado com `config` de callbacks | @test-generator | 1, 2, 3 |
| 11 | `docs/DEPLOYMENT.md` | Modify | Remove os passos de deploy no Streamlit Community Cloud; documenta o serviço único no Render com as novas env vars; atualiza o smoke test (seção 7) | (general) | 7 |
| 12 | `docs/ARCHITECTURE.md` | Modify | Atualiza o diagrama de containers (C4 nível 2) e o diagrama de sequência para refletir a fusão frontend+backend | (general) | 1, 2 |
| 13 | `README.md` | Modify | Atualiza o resumo de arquitetura ("Streamlit Chat" → "Chainlit UI, montado no FastAPI") e instruções de setup local | (general) | 7, 11 |

**Total Files:** 13 (10 modificados/criados + 4 removidos como um item agrupado)

---

## Agent Assignment Rationale

> Agentes descobertos em `${CLAUDE_PLUGIN_ROOT}/agents/**/*.md` — Build invoca os especialistas indicados.

| Agent | Files Assigned | Why This Agent |
|-------|----------------|-----------------|
| @python-developer | 1, 2, 3 | "Python code architect for data engineering systems — clean patterns, dataclasses, type hints" — encaixa no estilo já usado em `graph.py`/`main.py` (funções assíncronas tipadas, sem framework OOP pesado) |
| @test-generator | 10 | "Test automation expert for Python. Generates pytest unit tests, integration tests, and fixtures" — o projeto já usa pytest (`backend/tests/test_fabric_tools.py`) |
| (general) | 4, 5, 6, 7, 8, 9, 11, 12, 13 | Nenhum agente do catálogo é especialista em Render.com, Docker Compose puro ou edição de Markdown de documentação — são mudanças de configuração/infra simples, tratadas diretamente no Build |

**Agent Discovery:**
- Buscado por: tipo de arquivo (`.py` → python-developer; testes → test-generator), palavras-chave de propósito ("streaming", "auth callback" → python-developer), ausência de especialista dedicado a Render/Docker Compose no catálogo atual

---

## Code Patterns

### Pattern 1: Ponto de entrada do Chainlit (`backend/app/chainlit_app.py`)

```python
# Padrão: auth + chat profiles + starters + on_message com streaming.
# Confiança: alta para on_message/password_auth_callback/user_session (APIs centrais do
# Chainlit); moderada para nomes exatos de ChatProfile/Starter/LangchainCallbackHandler —
# confirmar contra a versão instalada antes de codar (ver Decisão 2 e 3).

from __future__ import annotations

import os
import uuid

import chainlit as cl

from app.agent.graph import run_agent
from app.audit.logger import write_audit

APP_USERNAME = os.getenv("APP_USERNAME")
APP_PASSWORD = os.getenv("APP_PASSWORD")

DOMAIN_LABELS = {"ar": "Contas a Receber", "fabric": "Fabric — Pipeline de Vendas"}


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    if username == APP_USERNAME and password == APP_PASSWORD:
        return cl.User(identifier=username)
    return None


@cl.set_chat_profiles
async def chat_profiles() -> list[cl.ChatProfile]:
    return [
        cl.ChatProfile(name="ar", markdown_description=DOMAIN_LABELS["ar"]),
        cl.ChatProfile(name="fabric", markdown_description=DOMAIN_LABELS["fabric"]),
    ]


@cl.set_starters
async def starters() -> list[cl.Starter]:
    # Confirmar no Build se `set_starters` recebe o chat_profile atual ou é global;
    # se for global, filtrar a lista dentro de on_chat_start em vez daqui.
    return [
        cl.Starter(label="Qual o saldo total em aberto?", message="Qual o saldo total em aberto?"),
        cl.Starter(label="Mostre o aging por faixa de atraso", message="Mostre o aging por faixa de atraso"),
    ]


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("session_id", str(uuid.uuid4()))
    domain = cl.user_session.get("chat_profile") or "ar"
    cl.user_session.set("domain", domain)


@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id")
    domain = cl.user_session.get("domain", "ar")

    handler = cl.LangchainCallbackHandler()
    result = await run_agent(
        user_message=message.content,
        session_id=session_id,
        domain=domain,
        config={"callbacks": [handler]},
    )

    elements = []
    if result.get("data"):
        elements.append(cl.Dataframe(data=result["data"], display="inline"))
    if result.get("chart_spec"):
        elements.append(_build_plotly_element(result["chart_spec"]))

    answer = result.get("answer", "Não foi possível gerar uma resposta.")
    lineage_md = _render_lineage_markdown(result.get("lineage"))
    if lineage_md:
        answer += f"\n\n{lineage_md}"

    await cl.Message(content=answer, elements=elements).send()

    try:
        write_audit(
            session_id=session_id,
            user_message=message.content,
            agent_plan=result.get("plan"),
            tools_called=result.get("tools_called"),
            final_sql=result.get("final_sql"),
            response_summary=answer[:500],
            lineage=result.get("lineage"),
            latency_ms=result.get("latency_ms"),
        )
    except Exception:
        pass  # mesmo comportamento tolerante a falha do main.py atual
```

### Pattern 2: Linhagem como Markdown colapsável (evita depender de um elemento incerto)

```python
# Renderiza a linhagem como bloco <details> em Markdown — funciona em qualquer versão
# do Chainlit, sem depender de uma classe de elemento específica não verificada em KB.

def _render_lineage_markdown(lineage: dict | None) -> str | None:
    if not lineage:
        return None
    views = lineage.get("views") or []
    views_md = "\n".join(f"- `{v.get('view')}` — {v.get('description') or ''}" for v in views)
    sql_md = f"\n```sql\n{lineage['sql']}\n```" if lineage.get("sql") else ""
    return (
        "<details>\n<summary>📍 Origem do dado (linhagem)</summary>\n\n"
        f"**Camada:** `{lineage.get('layer', '—')}`\n\n"
        f"**Sistema de origem:** {lineage.get('source_system', '—')}\n\n"
        f"{views_md}{sql_md}\n</details>"
    )
```

### Pattern 3: `run_agent` aceitando `config` opcional (mudança aditiva em `graph.py`)

```python
# backend/app/agent/graph.py — assinatura muda de forma aditiva (default None),
# não quebra chamadas existentes nem backend/tests/test_fabric_tools.py.

from langchain_core.runnables import RunnableConfig

async def run_agent(
    user_message: str,
    session_id: str,
    domain: str = "ar",
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    ...
    return await _run_react_loop(..., config=config)


async def _run_react_loop(..., config: RunnableConfig | None = None) -> dict[str, Any]:
    ...
    response: AIMessage = await llm_with_tools.ainvoke(messages, config=config)
    ...
```

### Pattern 4: Variáveis de ambiente novas (`render.yaml` / `.env`)

```yaml
# Adições ao serviço único `gefin-backend` em render.yaml (todas sync: false —
# preenchidas manualmente no dashboard do Render, nunca commitadas)
- key: CHAINLIT_AUTH_SECRET
  sync: false
- key: APP_USERNAME
  sync: false
- key: APP_PASSWORD
  sync: false
```

---

## Data Flow

```text
1. Usuário abre a URL única do serviço (Render ou localhost:8000)
   │
   ▼
2. Chainlit exibe a tela de login → @cl.password_auth_callback valida
   APP_USERNAME/APP_PASSWORD; sessão assinada com CHAINLIT_AUTH_SECRET
   │
   ▼
3. @cl.on_chat_start: gera session_id (uuid4) em cl.user_session;
   lê o chat_profile escolhido (ar/fabric); exibe os starters daquele domínio
   │
   ▼
4. Usuário envia mensagem (digitada ou clicando num starter) → @cl.on_message
   │
   ▼
5. Handler chama run_agent(message, session_id, domain, config={"callbacks": [...]})
   diretamente (import Python, sem HTTP)
   │
   ▼
6. Loop ReAct roda como hoje (Plan → Tools → Reflect); o cl.LangchainCallbackHandler
   cria um cl.Step por tool call e streama os tokens da resposta final
   │
   ▼
7. run_agent retorna {answer, data, chart_spec, lineage, steps, ...} — handler
   monta cl.Dataframe + elemento de gráfico + bloco de linhagem em Markdown
   │
   ▼
8. write_audit(...) grava o registro de auditoria (mesma tabela audit_log de hoje)
```

---

## Integration Points

| External System | Integration Type | Authentication |
|-----------------|-------------------|-----------------|
| PostgreSQL (views semânticas) | SQLAlchemy/psycopg2, via tools do agente | `DATABASE_URL` (inalterado) |
| Fabric MCP remoto | `langchain-mcp-adapters`, via `fabric_mcp_tools()` | `MCP_AUTH_TOKEN` (inalterado) |
| LLM (Claude/OpenAI/Ollama) | LangChain chat models | `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/local (inalterado) |
| Render (hosting) | Deploy Docker, 1 serviço web free tier | N/A |

---

## Testing Strategy

| Test Type | Scope | Files | Tools | Coverage Goal |
|-----------|-------|-------|-------|----------------|
| Unit | `auth_callback` aceita credenciais corretas e rejeita incorretas (AT-002) | `backend/tests/test_chainlit_app.py` | pytest | 100% dos caminhos de auth |
| Unit | Mapeamento `chat_profile` → `domain` passado a `run_agent` (AT-001, AT-004) | `backend/tests/test_chainlit_app.py` | pytest + mock de `run_agent` | Happy path + fallback para `ar` |
| Integration | `GET /health`, `GET /catalog` respondem com o mesmo contrato após o `mount_chainlit` (AT-003) | `backend/tests/test_chainlit_app.py` | pytest + `fastapi.testclient.TestClient` | 100% das rotas preservadas |
| Integration | `run_agent` chamado com `config` contendo o callback handler, sem quebrar `backend/tests/test_fabric_tools.py` existente | `backend/tests/test_fabric_tools.py` (regressão) | pytest | Nenhuma regressão |
| E2E | Smoke test manual: login → pergunta → streaming perceptível → tabela/gráfico/linhagem renderizam → steps visíveis | Manual, roteiro em `docs/DEPLOYMENT.md` seção 7 | `docker compose up --build` | Happy path completo antes do corte de produção |

---

## Error Handling

| Error Type | Handling Strategy | Retry? |
|------------|---------------------|--------|
| Credenciais inválidas no login | `auth_callback` retorna `None`; Chainlit mostra erro genérico de autenticação | Não (usuário tenta de novo manualmente) |
| Falha na chamada ao LLM (já tratada em `graph.py`) | `run_agent` já retorna uma `answer` com mensagem de erro estruturada; handler exibe como mensagem normal do assistente | Não (mesmo comportamento do `st.error` atual) |
| Falha de conexão ao Fabric MCP (já tratada em `graph.py`) | Mesma resposta amigável já existente é repassada sem mudança | Não |
| `write_audit` falha | `except Exception: pass` (idêntico ao `main.py` atual) — não bloqueia a resposta ao usuário | Não |

---

## Configuration

| Config Key | Type | Default | Description |
|------------|------|---------|--------------|
| `CHAINLIT_AUTH_SECRET` | string | nenhum (obrigatório) | Segredo usado pelo Chainlit para assinar a sessão de login |
| `APP_USERNAME` | string | nenhum (obrigatório) | Usuário do login único compartilhado |
| `APP_PASSWORD` | string | nenhum (obrigatório) | Senha do login único compartilhado |

Demais variáveis (`LLM_PROVIDER`, `DATABASE_URL`, `MCP_*`, etc.) permanecem inalteradas.

---

## Security Considerations

- `CHAINLIT_AUTH_SECRET`, `APP_USERNAME`, `APP_PASSWORD` devem ser `sync: false` no `render.yaml` (preenchidos manualmente no dashboard, nunca commitados) — mesmo padrão já usado para `ANTHROPIC_API_KEY`/`MCP_AUTH_TOKEN`.
- A rota `POST /chat` é removida (Decisão 4) especificamente para que a autenticação não tenha um caminho de bypass via chamada HTTP direta ao backend.
- `/health` e `/catalog` continuam sem autenticação — aceitável porque não expõem dados de negócio nem executam SQL (apenas status e um resumo estático do catálogo).
- `CORSMiddleware(allow_origins=["*"])` em `main.py` permanece como estava — fora do escopo desta feature (nenhuma rota sensível depende mais de CORS depois que `/chat` sai); registrar como débito técnico pré-existente, não introduzido por esta migração.
- Rotação de senha/segredo é manual (sem gerenciador de segredos) — consistente com o porte de protótipo/portfólio já assumido no DEFINE.

---

## Observability

| Aspect | Implementation |
|--------|------------------|
| Logging | Mantém `logging` padrão do Python já usado em `main.py`/`graph.py` (nível `INFO`); Chainlit adiciona seus próprios logs de request, sem integração adicional nesta feature |
| Metrics | Nenhuma (fora de escopo, sem mudança em relação a hoje) |
| Tracing | Nenhum (fora de escopo, sem mudança em relação a hoje) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-12 | design-agent | Initial version, a partir de `DEFINE_CHAINLIT_FRONTEND_MIGRATION.md` |
| 1.1 | 2026-08-12 | ship-agent | Shipped and archived |

---

## Next Step

**Ready for:** `/build .claude/sdd/features/DESIGN_CHAINLIT_FRONTEND_MIGRATION.md`
