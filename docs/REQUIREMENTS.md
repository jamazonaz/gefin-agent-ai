# GEFIN Agent — Requirements Agentic (MVP Prototype)

> Requisitos agentic alinhados com a implementação atual  
> Baseado no BRAINSTORM_GEFIN_AGENT.md (2026-08-05)

**Status:** v1.0 — Implementado (esqueleto funcional)  
**Data:** 2026-08-06  
**Escopo:** MVP — Contas a Receber apenas  
**Ambiente:** Docker Compose · LLM configurável (Claude padrão)

---

## 1. Problem Statement

O time financeiro depende de navegar manualmente por relatórios Power BI de contas a receber. Não existe forma de:
- Perguntar em linguagem natural
- Gerar visualizações e KPIs sob demanda
- Ver a **origem rastreável** de cada número

O GEFIN Agent resolve isso com um **agente de analytics governado** que:
1. Entende a pergunta
2. Planeja a consulta
3. Usa tools controladas (nunca SQL livre em tabelas brutas)
4. Valida o resultado
5. Entrega resposta + gráfico/KPI + linhagem visível

---

## 2. Vision & Success Criteria (MVP)

### Success Criteria
- [x] Arquitetura agentic (Plan → Tools → Reflect) implementada
- [x] Toda resposta pode exibir **linhagem** (views + SQL)
- [x] Geração de gráficos dinâmicos (Plotly via `generate_chart`)
- [x] Follow-ups na mesma sessão (memória de curto prazo)
- [x] Interações auditadas (`audit_log`)
- [x] Zero acesso a tabelas brutas — apenas views whitelisted (sqlglot)
- [x] Sobe com `docker compose up --build`
- [ ] Validação ≥ 80% em perguntas típicas reais (próximo passo com dados/perguntas do usuário)

### Non-goals (MVP)
- Contas a pagar / Fluxo de caixa
- RLS por departamento
- Multi-agent hierárquico
- Lakehouse (Iceberg) / OpenMetadata
- Integração com Power BI XMLA
- Autenticação enterprise (SSO)

---

## 3. Agentic Architecture Requirements

### 3.1 Padrão de Agente
- **Single-agent** com loop **Plan → Act (Tools) → Observe → Reflect** (ReAct)
- O agente **não** gera SQL direto no prompt principal — decide quais **tools** chamar
- Máximo de iterações configurável (`MAX_AGENT_STEPS`, default 6)
- Fallback de linhagem se o modelo esquecer de chamar `get_lineage`

**Implementação:** `backend/app/agent/graph.py`

### 3.2 Tools (implementadas)

| Tool | Descrição | Guardrails |
|------|-----------|------------|
| `list_metrics` | Lista métricas/views do catálogo | Somente leitura |
| `get_metric_definition` | Detalhe de uma métrica | Somente leitura |
| `execute_sql` | SELECT só em views whitelisted | sqlglot + whitelist + LIMIT |
| `validate_result` | Checagens básicas de qualidade | Determinístico |
| `generate_chart` | Spec de gráfico (bar/line/pie) | Input = dados já obtidos |
| `get_lineage` | Origem (views + SQL + nota) | Sempre na resposta final |

### 3.3 Memory
- **Short-term (session):** histórico da conversa em memória de processo
- **Long-term:** fora do MVP

### 3.4 Guardrails & Safety
- Whitelist explícita de views (vinda do catálogo YAML)
- SQL validado com **sqlglot** (apenas SELECT; bloqueia DDL/DML)
- `LIMIT` automático se ausente
- Nenhuma tabela bruta acessível
- Toda tool call logada no audit

### 3.5 Observability & Audit
Tabela `audit_log` com: session_id, user_message, agent_plan, tools_called, final_sql, response_summary, lineage, latency_ms.

---

## 4. Data Requirements

### 4.1 Fonte
PostgreSQL local (Docker). Schema de Contas a Receber com volume realista (~40 clientes, centenas de faturas).

### 4.2 Camada Semântica
Views: `vw_ar_open_items`, `vw_ar_aging`, `vw_ar_customer_summary`, `vw_ar_kpi_daily`, `vw_ar_dso`.

### 4.3 Catálogo
`catalog/metrics.yaml` — métricas, dimensões, views, exemplos de perguntas.

---

## 5. Interface Requirements

- Chat web (Chainlit, montado no FastAPI) com login único e resposta em streaming
- Texto + tabelas + gráficos Plotly + bloco de linhagem
- Histórico de sessão
- Perguntas-exemplo por assistente (starters)

---

## 6. Non-Functional Requirements

| Requisito | Meta / Status |
|-----------|----------------|
| Deploy | `docker compose up --build` ✅ |
| LLM padrão | Anthropic Claude ✅ |
| LLM alternativo | OpenAI ou Ollama (`--profile ollama`) ✅ |
| Segurança de SQL | sqlglot + whitelist ✅ |
| Portabilidade | Linux / macOS / Windows + Docker ✅ |

---

## 7. Out of Scope (confirmado)

- Contas a pagar, Fluxo de caixa
- Iceberg / MinIO / OpenMetadata
- Multi-agent
- RLS / multi-tenancy
- Autenticação real
- Power BI integration

---

## 8. Acceptance Criteria (Definition of Done do MVP)

1. [x] `docker compose up --build` sobe db + backend + frontend (+ adminer)
2. [x] Usuário abre o chat e envia perguntas em português
3. [x] Agente usa tools (catalog, SQL, lineage…)
4. [x] Resposta pode incluir tabela + gráfico + linhagem
5. [x] Logs de auditoria são gravados
6. [x] Nenhuma query toca tabela bruta
7. [x] README documenta Claude como caminho principal
8. [ ] Validação empírica com lista real de perguntas do time financeiro

---

*Documento alinhado com o código em `gefin-agent/` (2026-08-06).*
