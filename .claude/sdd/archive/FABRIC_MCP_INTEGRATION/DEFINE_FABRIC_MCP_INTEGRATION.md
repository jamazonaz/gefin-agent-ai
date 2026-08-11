# DEFINE: Fabric MCP Integration (Sales Pipeline Assistant)

> Adiciona um segundo "assistente" ao GEFIN Agent, selecionável no chat, que responde perguntas em linguagem natural sobre o modelo semântico de Pipeline de Vendas do Fabric/Power BI via MCP, com gráficos e linhagem de consulta.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FABRIC_MCP_INTEGRATION |
| **Date** | 2026-08-11 |
| **Author** | define-agent |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O time financeiro/comercial que usa o GEFIN Agent hoje só consegue perguntar sobre Contas a Receber (Postgres); para saber sobre Pipeline de Vendas (Revenue, Forecast, Win/Loss), precisa abrir o Power BI manualmente e navegar entre 11 páginas de relatório e medidas DAX sem contexto de negócio, sem conseguir perguntar em linguagem natural nem ver de onde o número veio.

---

## Target Users

| User | Role | Pain Point |
|------|------|------------|
| Analista comercial/financeiro | Consumidor do relatório de Pipeline de Vendas no Power BI | Precisa abrir o Power BI, navegar 11 páginas e conhecer as medidas DAX de cor para responder perguntas simples como "qual o Revenue Won por indústria?" |
| Usuário atual do GEFIN Agent | Já usa o chat para Contas a Receber | Quer uma segunda fonte de dados governada no mesmo chat, sem que as respostas de AR e Vendas se misturem ou percam a linhagem |

---

## Goals

| Priority | Goal |
|----------|------|
| **MUST** | Usuário escolhe o assistente (AR ou Fabric/Vendas) ao abrir um novo chat; cada sessão carrega só o toolset do domínio escolhido |
| **MUST** | Agente Fabric responde com dado real obtido via `execute_dax_query` (MCP), nunca valor alucinado, para as 15 medidas do catálogo |
| **MUST** | `catalog/fabric_metrics.yaml` cobre as 10 tabelas e 15 medidas descobertas, com descrição e exemplo de pergunta por medida, seguindo o mesmo formato de `catalog/metrics.yaml` |
| **MUST** | Toda resposta do assistente Fabric inclui um bloco de linhagem: medidas/tabelas usadas na consulta DAX + página do report relacionada (quando mapeável) |
| **SHOULD** | Integração MCP↔LangChain via `langchain-mcp-adapters`, com sessão MCP aberta uma vez por turno de chat (não por tool call) |
| **SHOULD** | Gráficos do assistente Fabric reaproveitam a tool `generate_chart`/Plotly já existente, sem depender de embed real do Power BI |
| **SHOULD** | Variáveis `MCP_SERVER_URL` e `MCP_AUTH_TOKEN` propagadas para `render.yaml` (deploy), não só `.env` local |
| **COULD** | Guardrail leve no DAX (`execute_dax_query` só aceita `EVALUATE`; tabelas referenciadas validadas contra a whitelist do catálogo) |
| **COULD** | Variante do `triage_scope` para o domínio Fabric, recusando perguntas de AR/fora de escopo dentro da sessão Fabric |

---

## Success Criteria

- [ ] Seletor de assistente (AR | Fabric) funcional no frontend Streamlit ao iniciar novo chat, 100% das sessões carregam o toolset correto para o domínio escolhido
- [ ] As 15 medidas do catálogo Fabric (`catalog/fabric_metrics.yaml`) respondem com dado real via `execute_dax_query` em teste manual (0 respostas alucinadas)
- [ ] 100% das respostas do assistente Fabric incluem bloco de linhagem (medidas/tabelas + página do report, quando mapeável)
- [ ] `catalog/fabric_metrics.yaml` cobre as 10 tabelas e 15 medidas descobertas nesta sessão, com pelo menos 1 exemplo de pergunta cada
- [ ] Gráfico (bar/line) gerado com sucesso para pelo menos 1 medida temporal e 1 categórica, reaproveitando `generate_chart`

---

## Acceptance Tests

| ID | Scenario | Given | When | Then |
|----|----------|-------|------|------|
| AT-001 | Happy path — pergunta sobre medida do catálogo | Usuário abriu novo chat e selecionou o assistente "Fabric" | Pergunta "Qual o Revenue Won total?" | Agente consulta o catálogo, chama `execute_dax_query`, retorna o valor real e um bloco de linhagem citando a medida `Opportunities[Revenue Won]` |
| AT-002 | Erro do MCP não vira alucinação | Assistente Fabric selecionado | `execute_dax_query` retorna erro (timeout, cold start do Render, ou 400 de permissão) | Agente comunica o erro claramente ao usuário, sem inventar um valor nem travar o loop ReAct |
| AT-003 | Pergunta fora do domínio Fabric | Assistente Fabric selecionado | Usuário pergunta algo de Contas a Receber (ex: "qual o saldo em aberto?") | Agente responde que está fora do escopo do assistente atual e sugere trocar para o assistente AR |

---

## Out of Scope

- Embedding real de visuais/relatório do Power BI no frontend (o MCP não retorna embed token nem definição visual).
- Lineage ponta-a-ponta estilo Purview (fica registrada como roadmap futuro).
- Descoberta de schema em tempo real a cada pergunta do usuário (catálogo é estático, atualizado via script quando o modelo mudar).
- Roteamento automático entre os domínios AR e Fabric numa mesma sessão de chat.
- Qualquer operação de escrita no Fabric/Power BI (DAX/`EVALUATE` é inerentemente read-only).

---

## Constraints

| Type | Constraint | Impact |
|------|------------|--------|
| Technical | O MCP expõe só 3 tools (`execute_dax_query`, `list_report_pages`, `list_report_visuals`), sem tool de metadata dedicada | Schema precisa ser descoberto uma vez via DAX `INFO.VIEW.*` e materializado em `catalog/fabric_metrics.yaml`, não consultado sob demanda |
| Technical | `INFO.TABLES()`/`INFO.MEASURES()` (DMVs de nível admin) retornam erro 400 com as permissões atuais do Service Principal | Só as funções `INFO.VIEW.*` (nível "view") funcionam para descoberta de schema |
| Resource | Servidor MCP hospedado no Render (plano/tier não confirmado) | Validar cold start e timeout no Build; pode exigir loading state mais explícito no frontend |
| Technical | Stack já usa LangChain (`bind_tools`, `ALL_TOOLS`) de forma síncrona dentro de um loop assíncrono | Integração MCP precisa respeitar esse padrão (`langchain-mcp-adapters`, sessão async por turno) sem quebrar o restante do `graph.py` |

---

## Technical Context

| Aspect | Value | Notes |
|--------|-------|-------|
| **Deployment Location** | `backend/app/agent/` (novas tools + prompts), `backend/app/catalog/` (loader estendido ou novo), `catalog/fabric_metrics.yaml` (novo), `frontend/app.py` (seletor de assistente), `render.yaml` + `.env.example` (novas env vars) | Espelha a estrutura existente do domínio AR (catálogo → tools → prompt → frontend) |
| **KB Domains** | `microsoft-fabric` (semantic-link, power-bi-api patterns), `genai` (tool-calling, agentic-workflow, chatbot-architecture), `python` (async patterns, error-handling) | `microsoft-fabric` cobre padrões de API/SDK do Fabric; `genai` cobre tool-calling multi-domínio e arquitetura de chatbot |
| **IaC Impact** | Modify existing | Adicionar `MCP_SERVER_URL` e `MCP_AUTH_TOKEN` ao `render.yaml` do backend e ao `.env.example`; sem novos recursos de infraestrutura |

---

## Data Contract (if applicable)

### Source Inventory
| Source | Type | Volume | Freshness | Owner |
|--------|------|--------|-----------|-------|
| Fabric Semantic Model (via MCP, `execute_dax_query`) | Power BI/Fabric semantic model, modo Import | Dataset de amostra "Sales & Marketing Sample" (baixo volume) | Depende do refresh do modelo no Fabric — fora do controle do GEFIN Agent | Workspace Fabric (externo) |

### Schema Contract
| Column | Type | Constraints | PII? |
|--------|------|-------------|------|
| `Opportunities[Revenue Won]`, `[Revenue In Pipeline]`, `[Revenue Open]`, `[Forecast]` | Integer/Number | Medidas DAX, não colunas brutas | No |
| `Opportunities[Forecast %]`, `[Close %]` | Number | Percentuais calculados | No |
| Colunas de `Contacts`/`Accounts` (não exploradas em detalhe nesta sessão) | Text | — | **A confirmar no Build** — tabela `Contacts` pode conter nomes/e-mails mesmo em dataset de amostra |

### Freshness SLAs
| Layer | Target | Measurement |
|-------|--------|-------------|
| Fabric Semantic Model | N/A — refresh controlado pelo Fabric, fora do escopo do GEFIN Agent | Não aplicável; tratar como fonte externa, sem SLA própria |

### Completeness Metrics
- Erros do `execute_dax_query` (timeout, permissão, cold start) devem ser sempre surfaced ao usuário, nunca silenciosamente engolidos (proxy de completude/confiabilidade, já que não há como medir completude do dataset externo).

### Lineage Requirements
- Linhagem de consulta: medidas/tabelas DAX usadas na resposta.
- Página do report relacionada (via `list_report_pages`/`list_report_visuals`), quando mapeável — mapeamento é aproximado, não uma ligação direta medida→visual exposta pelo MCP.
- Lineage ponta-a-ponta (Purview) fora de escopo (ver Out of Scope).

---

## Assumptions

| ID | Assumption | If Wrong, Impact | Validated? |
|----|------------|-------------------|------------|
| A-001 | O servidor MCP no Render pode ter cold start, afetando a latência da primeira request de uma sessão | Precisaria de loading state mais explícito no frontend ou um "ping" de aquecimento | [ ] |
| A-002 | `langchain-mcp-adapters` é compatível com as versões já pinadas `mcp==1.29.0` e `langchain-core==0.3.29` | Se não for, cai para Approach B (tools escritas à mão) ou exige bump de versão com regressão a validar | [ ] |
| A-003 | Não existe forma de mapear medida→visual/página com precisão via MCP (só contagem de visuais por tipo, por página) | O campo "página do report" na linhagem será omitido ou aproximado para várias medidas, não garantido para todas | [x] — confirmado nesta sessão via `list_report_visuals` |
| A-004 | Tabelas como `Contacts` podem conter dados pessoais (nome, e-mail) mesmo sendo dataset de amostra | Cat álogo/tools não devem expor colunas dessas tabelas sem revisão; tratar como não-whitelisted até confirmar no Build | [ ] |

**Note:** Validar A-001, A-002 e A-004 antes ou durante o Build.

---

## Clarity Score Breakdown

| Element | Score (0-3) | Notes |
|---------|-------------|-------|
| Problem | 3 | Herdado do BRAINSTORM, específico sobre quem sofre (analista comercial/financeiro) e o impacto (navegar 11 páginas manualmente sem linguagem natural) |
| Users | 3 | Duas personas com pain points claros e distintos |
| Goals | 3 | MoSCoW completo, derivado das decisões e approach confirmados no BRAINSTORM |
| Success | 2 | Critérios majoritariamente mensuráveis (contagens, 100%), mas sem número de latência/performance alvo — deixado para Design definir SLA técnico |
| Scope | 3 | Out of Scope explícito com 5 itens, todos rastreáveis a decisões do BRAINSTORM |
| **Total** | **14/15** | |

**Minimum to proceed: 12/15** ✅

---

## Open Questions

- Confirmar o plano/tier do servidor Render do MCP (afeta tolerância a cold start — ver A-001).
- Decidir a política de tratamento de PII para tabelas como `Contacts` antes de expor qualquer coluna no catálogo (ver A-004).
- Validar durante o Build a compatibilidade de versão de `langchain-mcp-adapters` com `mcp==1.29.0`/`langchain-core==0.3.29` (ver A-002) — se incompatível, reavaliar Approach B do BRAINSTORM.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-11 | define-agent | Versão inicial, extraída de `BRAINSTORM_FABRIC_MCP_INTEGRATION.md` |
| 1.1 | 2026-08-11 | ship-agent | Shipped and archived |

---

## Next Step

**Ready for:** `/ship .claude/sdd/features/DEFINE_FABRIC_MCP_INTEGRATION.md`
