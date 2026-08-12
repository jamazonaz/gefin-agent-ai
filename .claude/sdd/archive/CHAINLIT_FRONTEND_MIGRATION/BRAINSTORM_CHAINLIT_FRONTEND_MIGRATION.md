# BRAINSTORM: Chainlit Frontend Migration

> Exploratory session to clarify intent and approach before requirements capture

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | CHAINLIT_FRONTEND_MIGRATION |
| **Date** | 2026-08-12 |
| **Author** | brainstorm-agent |
| **Status** | ✅ Shipped |

---

## Initial Idea

**Raw Input:** "Gostaria de implementar em meu frontend o Chainlit (https://github.com/Chainlit/chainlit) no lugar do Streamlit, já que estou evoluindo o projeto — qual o impacto?"

**Context Gathered:**
- Frontend atual é um único arquivo `frontend/app.py`, Streamlit puro (~200 linhas): `st.chat_message`/`st.chat_input`, `st.session_state`, sidebar com seletor de domínio (`ar`/`fabric`) e botões de pergunta-exemplo, `st.dataframe`, gráficos via `plotly.express` + `st.plotly_chart`, `st.expander` para linhagem (views + SQL), `st.spinner` durante o loop do agente.
- Backend (`backend/app/main.py`) é FastAPI puro, com um único endpoint relevante `POST /chat` que chama `run_agent(user_message, session_id, domain)` — uma função assíncrona **importável e desacoplada** de `app.agent.graph`, sem dependência do objeto `Request`/`Response`. Isso viabiliza chamar o agente in-process em vez de via HTTP.
- `ChatResponse` (`main.py:41-47`) já inclui um campo `steps: list[str] | None` — calculado no backend, mas **nunca renderizado** pelo `app.py` atual do Streamlit. Dado disponível de graça, hoje descartado.
- Deploy de produção (feature já shipada `FREE_TIER_PRODUCTION_DEPLOY`): backend no Render (free tier, sofre cold start após 15 min de inatividade) + frontend no Streamlit Community Cloud (free tier), conectados via secret `BACKEND_URL`. Sem autenticação — app público. Sem CI/testes automatizados antes de deploy; validação é um smoke test manual documentado (`docs/DEPLOYMENT.md`, seção 7).
- Schema do banco (`db/init/01_schema.sql`) não tem tabela de usuários — só `audit_log.user_message` (coluna de texto, não de identidade). Nenhuma infra de auth para reaproveitar.
- Projeto se descreve como "Portfólio project" (README) — otimizar para simplicidade é uma prioridade explícita do dono.

**Technical Context Observed (for Define):**

| Aspect | Observation | Implication |
|--------|-------------|-------------|
| Likely Location | `frontend/app.py` (reescrito), `backend/app/main.py` (montagem do Chainlit), `frontend/requirements.txt`, `frontend/Dockerfile` | Migração toca frontend e o entrypoint do backend |
| Relevant KB Domains | Nenhum domínio de KB cobre frontend/Chainlit — recomendações desta sessão vêm de evidência de código + conhecimento geral, não de padrão validado em KB | Define deve tratar decisões de UI/auth como julgamento documentado, não como padrão certificado |
| IaC Patterns | `render.yaml` (Render Blueprint) + Docker Compose local — hoje declara 2 serviços web (backend + frontend Streamlit Cloud não é gerenciado por `render.yaml`) | Corte para 1 serviço único no Render; `render.yaml` precisa refletir a fusão |

---

## Discovery Questions & Answers

| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | O que está motivando a troca de Streamlit por Chainlit? | (a) UX de streaming token-a-token + (c) autenticação (não: exibir raciocínio do agente) | Escopo focado em streaming + login; visibilidade de chain-of-thought não é requisito central (embora tenha sido adicionada depois por ser "de graça") |
| 2 | Como lidar com hosting, já que Chainlit não tem "Community Cloud" gratuito equivalente ao Streamlit? | Fundir frontend+backend, montando Chainlit dentro do FastAPI existente (`mount_chainlit`), preservando a API REST atual | Define arquitetura: 1 serviço Render em vez de 2; `run_agent()` chamado in-process, habilitando streaming real |
| 3 | Quem precisa logar, e como? | Login único compartilhado (`@cl.password_auth_callback`); contas individuais/OAuth removidos por YAGNI | Sem necessidade de tabela de usuários nem fluxo de cadastro |
| 4 | Existe alguma referência (app Chainlit visto, mockup) para basear a UX? | Nenhuma — propor do zero com base no que o Chainlit oferece nativamente | Define/Design têm liberdade total de UX dentro dos componentes nativos do Chainlit |

**Minimum Questions:** 3 ✅ (4 perguntas de descoberta + 1 pergunta de escopo dedicada sobre o campo `steps`)

---

## Sample Data Inventory

| Type | Location | Count | Notes |
|------|----------|-------|-------|
| Input files | N/A | — | Não aplicável — migração de UI, não de dados |
| Output examples | N/A | — | Nenhuma referência de UX/mockup disponível (confirmado pelo usuário) |
| Ground truth | N/A | — | Não aplicável |
| Related code | `frontend/app.py` (implementação atual completa) | 1 | Fonte da verdade para paridade de funcionalidade: chat history, dataframe, gráfico Plotly, expander de linhagem, sidebar (seletor de domínio + exemplos) |

**How samples will be used:**

- `frontend/app.py` atual serve como checklist de paridade funcional — cada `st.*` usado hoje precisa de um equivalente Chainlit mapeado no Design.
- `ChatResponse` (schema Pydantic em `main.py:41-47`) define o contrato de dados que a nova UI precisa renderizar, incluindo o campo `steps` hoje não utilizado.

---

## Approaches Explored

### Approach A: Fusão via `mount_chainlit`, corte direto (big-bang) ⭐ Recomendado

**Description:** Chainlit é montado dentro do FastAPI existente (`backend/app/main.py`), preservando `/health`, `/catalog`, `/chat`. O handler do Chainlit chama `run_agent()` diretamente (in-process). Login único via `@cl.password_auth_callback`. Corte é direto: valida local com `docker compose`, roda o smoke test manual existente, troca a URL de produção de uma vez, desliga o Streamlit Community Cloud.

**Pros:**
- Streaming token-a-token viável sem SSE/WebSocket entre serviços (motivação central do usuário).
- Um único serviço no Render — menos cold start, menos superfície de deploy free-tier.
- Login único protege o único ponto de entrada — sem lacuna de bypass via backend exposto separadamente.
- API REST (`/health`, `/catalog`) preservada para eventuais consumidores futuros.

**Cons:**
- Acopla o ciclo de vida de deploy do chat UI ao do backend.
- Sem período de paralelismo — se o smoke test manual deixar passar um problema, o usuário sente na primeira sessão em produção.

**Why Recommended:** O projeto já opera sem CI automatizado, com validação manual local antes de qualquer deploy (`docs/DEPLOYMENT.md`, seção 7) — adicionar uma fase de paralelismo (Approach B) duplicaria manutenção (dois serviços, dois `BACKEND_URL` sincronizados) sem reduzir risco real, dado o processo de validação já existente e o porte do projeto (portfólio, time interno pequeno). Confirmado pelo usuário.

---

### Approach B: Rodar em paralelo por um tempo

**Description:** Chainlit sobe como novo serviço; Streamlit continua no ar. Comparação por alguns dias antes de desligar o antigo.

**Pros:**
- Rollback trivial (apontar de volta para o Streamlit).

**Cons:**
- Mantém dois serviços free-tier simultâneos (mais um cold start no orçamento).
- Dois `BACKEND_URL`/configurações para manter sincronizados durante a janela de comparação.
- Esforço de manutenção duplicado por um ganho de segurança pequeno, dado o tamanho e o processo de validação já manual do projeto.

**Why Not Recommended:** Rejeitado pelo usuário — custo de coordenação não compensa para uma troca já validada localmente antes do corte.

---

## Data Engineering Context

Não aplicável — esta é uma migração de camada de apresentação (frontend), não altera pipeline de dados, schema ou fluxo de ingestão. O agente, as views semânticas e o catálogo permanecem inalterados.

**Nota de direção futura (fora de escopo agora):** o usuário mencionou a possibilidade de conectar a fontes OLAP corporativas no futuro — isso é evolução de arquitetura de dados, independente desta migração de frontend, e não deve ser misturado ao escopo desta feature.

---

## Selected Approach

| Attribute | Value |
|-----------|-------|
| **Chosen** | Approach A — Fusão via `mount_chainlit`, corte direto |
| **User Confirmation** | 2026-08-12, confirmado em duas validações incrementais (arquitetura/auth e migração/escopo de UI) |
| **Reasoning** | Menor esforço de manutenção, streaming viável sem duplicar rede, autenticação coesa num único ponto de entrada, alinhado ao processo de validação manual já existente no projeto |

---

## Key Decisions Made

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|----------------------|
| 1 | Montar Chainlit dentro do FastAPI existente (`mount_chainlit`), não como serviço separado | Elimina a viagem de rede entre frontend e backend, viabilizando streaming real; preserva API REST atual; reduz de 2 para 1 serviço free-tier | Chainlit como serviço standalone falando com o backend via HTTP (perderia streaming fácil e duplicaria cold start) |
| 2 | Login único compartilhado via `@cl.password_auth_callback` | Resolve o problema real (app hoje é 100% público) com esforço mínimo; não há tabela de usuários para reaproveitar | Contas individuais por analista; OAuth via provedor externo |
| 3 | Migração em corte direto (big-bang), sem período de paralelismo | Processo de validação do projeto já é manual e local antes de deploy; paralelismo duplicaria manutenção sem reduzir risco real | Rodar Chainlit e Streamlit em paralelo por alguns dias antes de desligar o antigo |
| 4 | Exibir o campo `steps` (chain-of-thought do agente) na nova UI, sempre visível | Dado já é calculado pelo backend e descartado hoje pelo Streamlit — custo de renderizar é quase zero | Deixar de fora por não ter sido motivação original (revertido após o usuário confirmar que valia incluir) |

---

## Features Removed (YAGNI)

| Feature Suggested | Reason Removed | Can Add Later? |
|-------------------|----------------|----------------|
| Contas individuais por analista (login por pessoa) | Não há tabela de usuários hoje; não resolve o problema central (acesso público indevido) melhor que login único; esforço extra sem necessidade comprovada num protótipo de portfólio | Yes |
| OAuth via provedor externo (Google/Microsoft/GitHub) | Mesmo raciocínio acima — complexidade de integração não justificada para o porte atual do projeto | Yes |
| Período de deploy em paralelo (Chainlit + Streamlit simultâneos) | Duplicaria manutenção de dois serviços free-tier e duas configurações sem reduzir risco real, dado que a validação já é manual e local antes do corte | Yes, se o projeto crescer e precisar de rede de segurança automatizada |
| Conexão a OLAP corporativo | Fora do escopo de uma migração de frontend — é evolução de arquitetura de dados, mencionada pelo usuário como direção futura, não requisito atual | Yes — candidata a brainstorm/feature própria no futuro |

---

## Incremental Validations

| Section | Presented | User Feedback | Adjusted? |
|---------|-----------|---------------|-----------|
| Arquitetura & Autenticação (fusão via `mount_chainlit`, login único) | ✅ | "Está sim. Para o futuro podemos conectar via OLAP da organização." | Não (nota de escopo futuro registrada, sem alterar o desenho atual) |
| Migração & Escopo de UI (corte direto, streaming, `steps`, paridade com dataframe/gráfico/linhagem) | ✅ | "Sim faz sentido" | Não |

**Minimum Validations:** 2 ✅

---

## Suggested Requirements for /define

### Problem Statement (Draft)

O frontend Streamlit atual não oferece streaming de resposta nem autenticação, e a migração para Chainlit exige reestruturar a topologia de deploy (hoje 2 serviços free-tier) sem quebrar a API REST existente nem o processo de validação manual já em uso.

### Target Users (Draft)

| User | Pain Point |
|------|------------|
| Analista financeiro (time interno) | Espera a resposta completa aparecer de uma vez (sem streaming); acessa um app 100% público, sem login |
| Mantenedor do projeto (dono/portfólio) | Mantém 2 serviços free-tier separados; quer reduzir superfície de deploy e aproveitar dado (`steps`) já calculado e hoje descartado |

### Success Criteria (Draft)

- [ ] Resposta do agente aparece em streaming (token a token) na nova UI
- [ ] App exige login único compartilhado antes de liberar o chat
- [ ] `/health`, `/catalog` e o comportamento equivalente a `/chat` continuam funcionando após a fusão
- [ ] Paridade funcional com o Streamlit atual: histórico de chat, tabela de dados, gráfico Plotly, bloco de linhagem (views + SQL)
- [ ] Passos do agente (`steps`) visíveis na UI, sem trabalho adicional no backend
- [ ] Deploy de produção roda em 1 único serviço Render (free tier), Streamlit Community Cloud desligado
- [ ] Smoke test manual (equivalente ao de `docs/DEPLOYMENT.md` seção 7) passa antes do corte de produção

### Constraints Identified

- Free tier em todos os serviços (Render) — sem orçamento para hosting pago
- Sem CI/testes automatizados antes de deploy — validação continua manual
- Sem tabela de usuários no banco — auth não pode depender de schema novo além do necessário para login único
- `run_agent()` deve continuar sendo chamado de forma compatível com o uso atual (domain `ar`/`fabric`, session_id, audit log via `write_audit`)

### Out of Scope (Confirmed)

- Contas individuais por analista ou OAuth externo
- Período de deploy em paralelo entre Chainlit e Streamlit
- Conexão a fontes OLAP corporativas (direção futura, feature própria)
- Qualquer mudança em pipeline de dados, schema ou views semânticas

---

## Session Summary

| Metric | Value |
|--------|-------|
| Questions Asked | 5 (4 de descoberta + 1 de escopo dedicada ao campo `steps`) |
| Approaches Explored | 2 (arquitetura/migração) |
| Features Removed (YAGNI) | 4 |
| Validations Completed | 2 |
| Duration | ~1 sessão de chat |

---

## Next Step

**Ready for:** `/define .claude/sdd/features/BRAINSTORM_CHAINLIT_FRONTEND_MIGRATION.md`
