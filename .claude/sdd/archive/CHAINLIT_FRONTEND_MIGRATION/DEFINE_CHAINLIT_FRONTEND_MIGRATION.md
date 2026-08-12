# DEFINE: Chainlit Frontend Migration

> Substituir o frontend Streamlit por Chainlit, montado dentro do FastAPI existente, para habilitar streaming de resposta e autenticação num único serviço free-tier.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | CHAINLIT_FRONTEND_MIGRATION |
| **Date** | 2026-08-12 |
| **Author** | define-agent |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O frontend Streamlit do GEFIN Agent responde de forma bloqueante (sem streaming) e não exige autenticação, deixando o chat público; além disso, a topologia de deploy atual (2 serviços free-tier no Render + Streamlit Community Cloud) duplica cold start e manutenção sem necessidade, já que o backend já expõe uma função de agente (`run_agent`) desacoplada o suficiente para ser chamada in-process por um frontend baseado em Chainlit.

---

## Target Users

| User | Role | Pain Point |
|------|------|------------|
| Analista financeiro | Usuário final do chat (time interno de Contas a Receber / Fabric) | Espera a resposta inteira renderizar de uma vez (sem streaming); acessa um app público sem login, sem controle de quem entra |
| Mantenedor do projeto | Dono/desenvolvedor do portfólio | Mantém 2 serviços free-tier separados (mais cold start, mais configuração); tem um campo `steps` já calculado pelo backend e descartado pelo frontend atual |

---

## Goals

| Priority | Goal |
|----------|------|
| **MUST** | Resposta do agente é exibida em streaming (token a token) na UI |
| **MUST** | Acesso ao chat exige autenticação (login único compartilhado) |
| **MUST** | Chainlit é montado dentro do FastAPI existente (`backend/app/main.py`), preservando `/health`, `/catalog` e o comportamento equivalente a `/chat` |
| **MUST** | Paridade funcional com o Streamlit atual: histórico de chat, tabela de dados, gráfico Plotly, bloco de linhagem (views + SQL), seletor de domínio (`ar`/`fabric`), perguntas-exemplo |
| **SHOULD** | Exibir os passos do agente (`steps`) já calculados pelo backend, hoje descartados pelo frontend |
| **SHOULD** | Deploy de produção passa a usar 1 único serviço Render (free tier), com o serviço do Streamlit Community Cloud desligado após o corte |
| **COULD** | Documentar, para evolução futura, a conexão a fontes OLAP corporativas (fora do escopo desta feature) |

**Priority Guide:**
- **MUST** = MVP fails without this
- **SHOULD** = Important, but workaround exists
- **COULD** = Nice-to-have, cut first if needed

---

## Success Criteria

Measurable outcomes:

- [ ] Primeiro token da resposta do agente aparece na UI antes da resposta completa estar pronta (streaming perceptível, não "tudo de uma vez" como hoje)
- [ ] 100% das rotas REST existentes (`/health`, `/catalog`, equivalente a `/chat`) respondem corretamente após a fusão com o Chainlit
- [ ] Acesso ao chat sem credenciais válidas é bloqueado (0% de acesso não autenticado)
- [ ] Paridade de 100% dos elementos visuais do Streamlit atual (tabela, gráfico, linhagem, seletor de domínio, botões de exemplo) presentes na nova UI
- [ ] Deploy de produção usa 1 serviço Render (redução de 2 → 1 serviço free-tier)
- [ ] Smoke test manual (equivalente ao de `docs/DEPLOYMENT.md` seção 7) passa 100% antes do corte de produção

---

## Acceptance Tests

| ID | Scenario | Given | When | Then |
|----|----------|-------|------|------|
| AT-001 | Happy path — chat com streaming | Usuário autenticado, sessão de chat aberta | Envia uma pergunta em linguagem natural sobre contas a receber | A resposta aparece em streaming (tokens incrementais), seguida de tabela/gráfico/linhagem quando aplicável, igual ao comportamento atual do Streamlit |
| AT-002 | Bloqueio de acesso sem login | Usuário não autenticado acessa a URL do app | Tenta abrir o chat | É redirecionado para a tela de login; não consegue enviar mensagens sem autenticar |
| AT-003 | API REST preservada após a fusão | Serviço único (Chainlit montado no FastAPI) no ar | Uma requisição é feita diretamente a `/health` ou `/catalog` | Responde com o mesmo contrato de hoje, sem exigir sessão de chat autenticada |
| AT-004 | Passos do agente visíveis | Usuário autenticado envia uma pergunta que aciona múltiplas tools (catálogo + SQL + gráfico) | O agente completa o loop Plan → Tools → Reflect | Os passos (`steps`) aparecem na UI de forma visível, sem exigir mudança no backend para serem calculados |

---

## Out of Scope

Explicitly NOT included in this feature:

- Contas individuais por analista (login por pessoa) ou OAuth via provedor externo (Google/Microsoft/GitHub) — login único compartilhado é suficiente para este MVP evoluído
- Período de deploy em paralelo entre Chainlit e Streamlit — a migração é corte direto (big-bang), validado localmente antes do corte
- Conexão a fontes OLAP corporativas — mencionada como direção futura, é uma feature própria de arquitetura de dados, independente desta migração de frontend
- Qualquer alteração em pipeline de dados, schema do banco, views semânticas ou lógica do agente (`run_agent`, tools) — escopo é estritamente a camada de apresentação e o ponto de montagem no backend
- Persistência de histórico de chat entre reinícios do servidor (hoje já é em memória por processo; esse comportamento não muda nesta feature)
- Feedback de mensagens (thumbs up/down) ou outros recursos nativos do Chainlit não relacionados a streaming, auth ou paridade funcional

---

## Constraints

| Type | Constraint | Impact |
|------|------------|--------|
| Technical | Sem tabela de usuários no banco (`db/init/01_schema.sql` não tem uma) | Autenticação não pode depender de schema novo além do mínimo necessário para login único compartilhado |
| Technical | `run_agent(user_message, session_id, domain)` deve continuar sendo a única porta de entrada para o agente, com o mesmo contrato de assinatura | Design não pode alterar a interface do agente; a UI apenas passa a chamá-la in-process em vez de via HTTP |
| Resource | Free tier em todos os serviços (Render) — sem orçamento para hosting pago | Arquitetura precisa caber em 1 serviço Render após a fusão; nada de serviços adicionais |
| Resource | Sem CI/testes automatizados antes de deploy (gap conhecido, documentado em `docs/DEPLOYMENT.md`) | Validação continua manual (smoke test local via `docker compose` antes do corte de produção) |
| Timeline | Nenhuma deadline externa — projeto de portfólio mantido por uma pessoa | Prioriza simplicidade de manutenção sobre robustez de processo (ex.: sem período de deploy em paralelo) |

---

## Technical Context

> Essential context for Design phase - prevents misplaced files and missed infrastructure needs.

| Aspect | Value | Notes |
|--------|-------|-------|
| **Deployment Location** | `backend/app/` (novo módulo de UI Chainlit montado no FastAPI existente); diretório `frontend/` é retirado de uso após o corte | Fusão decidida no Brainstorm (Approach A); Design define o nome exato do módulo/arquivo e como `mount_chainlit` é fiado ao `app` de `main.py` |
| **KB Domains** | Nenhum domínio de KB cobre frontend/Chainlit — este KB é focado em data engineering | Design deve se basear na documentação oficial do Chainlit (GitHub) e no código atual (`frontend/app.py`, `backend/app/main.py`) como referência, não em padrão de KB validado |
| **IaC Impact** | Modifica existente — `render.yaml` passa de 2 serviços web (backend + implícito frontend no Streamlit Cloud) para 1; `Dockerfile` do serviço único precisa instalar Chainlit em vez de Streamlit; `frontend/Dockerfile` e `frontend/requirements.txt` são removidos ou esvaziados | Nenhum recurso de infraestrutura novo (banco, fila, storage) é necessário |

**Why This Matters:**

- **Location** → Design phase uses correct project structure, prevents misplaced files
- **KB Domains** → Sem padrão de KB para seguir; Design precisa documentar as decisões de UI como julgamento próprio, citando a doc oficial do Chainlit
- **IaC Impact** → `render.yaml` e os Dockerfiles precisam refletir a fusão de serviços antes do corte de produção

---

## Data Contract

Não aplicável — esta feature não introduz, altera nem remove pipelines de dados, schemas de banco ou fontes de dados. O contrato de dados entre o agente e a UI (`ChatResponse`: `answer`, `data`, `chart_spec`, `lineage`, `steps`) já existe e permanece inalterado; a mudança é apenas em como e onde esse contrato é consumido (in-process em vez de via HTTP REST).

---

## Assumptions

Assumptions that if wrong could invalidate the design:

| ID | Assumption | If Wrong, Impact | Validated? |
|----|------------|------------------|------------|
| A-001 | Chainlit pode ser montado dentro de um app FastAPI existente (via `mount_chainlit` ou equivalente) sem quebrar as rotas REST já existentes (`/health`, `/catalog`) | Precisaria voltar a rodar Chainlit como serviço standalone, reintroduzindo 2 serviços e perdendo a chamada in-process ao agente | [ ] |
| A-002 | O elemento nativo de "steps"/chain-of-thought do Chainlit consegue renderizar o formato atual de `steps` (`list[str]`) sem exigir mudança no backend | Backend precisaria emitir uma estrutura mais rica (ex.: objetos com tipo de passo), adicionando trabalho fora do escopo original | [ ] |
| A-003 | O callback de autenticação nativo do Chainlit (usuário/senha único) é suficiente para proteger o app sem infraestrutura extra (sem tabela de usuários, sem serviço de identidade) | Precisaria avaliar uma solução de auth diferente, possivelmente exigindo schema novo | [ ] |
| A-004 | Chamar `run_agent()` diretamente de dentro de um handler do Chainlit (`@cl.on_message`) não introduz problemas de concorrência entre sessões simultâneas (ex.: estado compartilhado de cliente LLM) | Precisaria de isolamento adicional por sessão, aumentando a complexidade da integração in-process | [ ] |

**Note:** Validate critical assumptions before DESIGN phase. Unvalidated assumptions become risks.

---

## Clarity Score Breakdown

| Element | Score (0-3) | Notes |
|---------|-------------|-------|
| Problem | 3 | Problema específico e acionável: falta de streaming, falta de auth, topologia de deploy duplicada — todos evidenciados no código durante o Brainstorm |
| Users | 3 | Duas personas identificadas com dores concretas (analista financeiro / mantenedor do portfólio) |
| Goals | 3 | Metas com prioridade MoSCoW clara, derivadas diretamente das decisões confirmadas no Brainstorm |
| Success | 3 | Critérios testáveis e específicos (streaming perceptível, 100% das rotas preservadas, 0% acesso não autenticado, paridade de elementos, redução de serviços) |
| Scope | 2 | Out of Scope bem populado e confirmado pelo usuário; resta uma decisão de Design em aberto (layout exato de arquivos/módulos), por isso não é 3 |
| **Total** | **14/15** | Acima do gate de 12/15 — pronto para Design |

**Scoring Guide:**
- 0 = Missing entirely
- 1 = Vague or incomplete
- 2 = Clear but missing details
- 3 = Crystal clear, actionable

**Minimum to proceed: 12/15**

---

## Open Questions

- Layout exato de arquivos após a fusão (ex.: o código do Chainlit fica em `backend/app/chainlit_app.py`, ou o diretório `frontend/` é reaproveitado e referenciado pelo `mount_chainlit`?) — decisão de Design, não bloqueia o gate de clareza.
- Se `run_agent` usa LangChain internamente (indicado no diagrama de arquitetura, `docs/ARCHITECTURE.md`), Design deve confirmar se o streaming token-a-token é viável via callback nativo do LangChain integrado ao Chainlit, ou se exige um wrapper customizado.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-12 | define-agent | Initial version, extraído de `BRAINSTORM_CHAINLIT_FRONTEND_MIGRATION.md` |
| 1.1 | 2026-08-12 | ship-agent | Shipped and archived |

---

## Next Step

**Ready for:** `/design .claude/sdd/features/DEFINE_CHAINLIT_FRONTEND_MIGRATION.md`
