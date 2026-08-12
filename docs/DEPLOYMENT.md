# Deploy em Produção — GEFIN Agent

> Runbook reproduzível para publicar o GEFIN Agent usando apenas serviços com tier gratuito permanente.

---

## 1. Visão geral

Este guia publica o GEFIN Agent em dois serviços independentes: o backend FastAPI + Chainlit (Docker), num único serviço no **Render.com**, e o banco PostgreSQL no **Neon**. A UI de chat (Chainlit) é montada dentro do mesmo processo FastAPI que já serve `/health` e `/catalog` — não existe mais um serviço de frontend separado. Cada peça já é stateless e configurada por variável de ambiente (`DATABASE_URL`, `CATALOG_PATH`, `CHAINLIT_AUTH_SECRET`, etc.), então o deploy é apenas configuração de plataforma — nenhuma lógica de negócio muda. Os dois serviços rodam permanentemente em tier gratuito, sem necessidade de cartão de crédito.

---

## 2. Pré-requisitos

- Conta no GitHub, com o repositório já publicado e a branch `master` atualizada.
- Conta no [Render.com](https://render.com) (gratuita, sem cartão).
- Conta no [Neon](https://neon.tech) (gratuita, sem cartão).
- `psql` instalado localmente (cliente PostgreSQL), para rodar a migração do banco.
- Chainlit instalado localmente (`pip install chainlit`) apenas para gerar o segredo de autenticação no Passo 3 (`chainlit create-secret`).

---

## 3. Passo 1 — Criar o banco no Neon

1. Crie um projeto no Neon e, dentro dele, um database (o padrão `neondb` criado automaticamente serve).
2. Copie a connection string exibida no dashboard do projeto. O formato esperado é:

```text
postgresql://user:pass@host/db?sslmode=require&channel_binding=require
```

Guarde essa string — ela será usada tanto na migração (Passo 2) quanto na variável `DATABASE_URL` do backend no Render (Passo 3).

---

## 4. Passo 2 — Migrar o schema e os dados

A partir da raiz do repositório, rode o script de migração apontando para a connection string do Neon:

```bash
NEON_DATABASE_URL="postgresql://user:pass@host/db?sslmode=require&channel_binding=require" ./db/migrate_to_neon.sh
```

O script (`db/migrate_to_neon.sh`) aplica, em ordem, `01_schema.sql`, `02_sample_data.sql` e `03_views.sql` via `psql`, e ao final imprime a contagem de linhas das tabelas principais. A saída esperada é:

```text
customers | invoices | payments
-----------+----------+---------
        40 |      793 |     357
```

O próprio script avisa: ele **não é idempotente**. `01_schema.sql` usa `CREATE TABLE` sem `IF NOT EXISTS` e `02_sample_data.sql` usa `INSERT` puro sem proteção contra duplicação. Rode este script apenas uma vez por banco Neon — executá-lo de novo contra o mesmo banco falha em `01_schema.sql` (tabelas já existem) ou duplica os dados de exemplo, caso o schema seja alterado para permitir reexecução.

---

## 5. Passo 3 — Deploy do backend (FastAPI + Chainlit) no Render

1. No dashboard do Render, crie um novo **Blueprint** apontando para o repositório GitHub, branch `master`. O Render vai ler o `render.yaml` na raiz do repo automaticamente.
2. Confira que o serviço criado (`gefin-backend`) usa `runtime: docker`, `dockerfilePath: backend/Dockerfile` e `dockerContext: .` — o contexto de build precisa ser a raiz do repositório, não `backend/`, porque o Dockerfile copia `catalog/` de fora da pasta `backend/`.
3. Gere um segredo para assinar as sessões de login do Chainlit:

```bash
chainlit create-secret
```

4. As variáveis `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CHAINLIT_AUTH_SECRET`, `APP_USERNAME` e `APP_PASSWORD` estão declaradas como `sync: false` no `render.yaml` — o Render não recebe esses valores do blueprint por segurança. Preencha-as manualmente no dashboard do serviço, em **Environment**:
   - `DATABASE_URL`: a connection string do Neon copiada no Passo 1 (com `sslmode=require&channel_binding=require`).
   - `ANTHROPIC_API_KEY`: sua chave da Anthropic.
   - `CHAINLIT_AUTH_SECRET`: o valor gerado no passo 3 acima.
   - `APP_USERNAME` / `APP_PASSWORD`: as credenciais do login único compartilhado do time (escolha um usuário e senha fortes).
5. As demais variáveis (`PORT`, `CATALOG_PATH`, `LLM_PROVIDER`, `LLM_MODEL`, `LOG_LEVEL`, `MAX_AGENT_STEPS`, `SQL_ROW_LIMIT`, `SQL_TIMEOUT_SECONDS`) já vêm preenchidas pelo blueprint.
6. O Render usa `healthCheckPath: /health` para saber quando o deploy está saudável — acompanhe o build no painel de logs até o serviço ficar `Live`. Essa rota continua pública e não exige login.

**Comportamento do free tier:** o serviço entra em modo de espera ("spin down") após 15 minutos sem receber requisições. A próxima requisição após esse período sofre um cold start de cerca de 1 minuto até o container voltar a responder. O plano gratuito do Render oferece 750 horas/mês de execução, suficiente para manter um único serviço rodando o mês inteiro.

---

## 6. Passo 4 — Smoke test

Com o backend publicado, valide o fluxo completo:

1. Verifique o health check do backend:

```bash
curl https://<nome-do-servico>.onrender.com/health
```

2. Abra `https://<nome-do-servico>.onrender.com/chainlit` no navegador — é aqui que a UI de chat fica montada (não na raiz `/`).
3. Faça login com `APP_USERNAME`/`APP_PASSWORD` configurados no Passo 3.
4. Escolha o assistente (Contas a Receber ou Fabric) e envie a pergunta de teste: `Qual o saldo total em aberto?`
5. Confirme que a resposta aparece em streaming (token a token, não tudo de uma vez) e que a tabela, o gráfico e o bloco de linhagem renderizam como no protótipo local.
6. Confira que a resposta completa chega em até aproximadamente 60 segundos — esse teto já contempla o cold start do Render (~1 min) caso o backend estivesse parado.

---

## 7. Variáveis de ambiente

| Variável | Onde é configurada | Descrição |
|----------|---------------------|-----------|
| `PORT` | Render (`render.yaml`, valor fixo) | Porta fixa do Uvicorn (`8000`), declarada explicitamente para evitar depender da autodetecção do Render. |
| `DATABASE_URL` | Render (`sync: false`, manual) | Connection string do Neon (`postgresql://...?sslmode=require&channel_binding=require`). |
| `CATALOG_PATH` | Render (`render.yaml`, valor fixo) | Caminho do `metrics.yaml` dentro da imagem Docker (`/app/catalog/metrics.yaml`), copiado em build-time. |
| `LLM_PROVIDER` | Render (`render.yaml`, valor fixo) | Provedor de LLM (`anthropic`). |
| `LLM_MODEL` | Render (`render.yaml`, valor fixo) | Modelo usado (`claude-sonnet-4-20250514`). |
| `ANTHROPIC_API_KEY` | Render (`sync: false`, manual) | Chave de API da Anthropic. |
| `LOG_LEVEL` | Render (`render.yaml`, valor fixo) | Nível de log (`INFO`). |
| `MAX_AGENT_STEPS` | Render (`render.yaml`, valor fixo) | Limite de passos do loop do agente (`6`). |
| `SQL_ROW_LIMIT` | Render (`render.yaml`, valor fixo) | Limite de linhas retornadas por query (`500`). |
| `SQL_TIMEOUT_SECONDS` | Render (`render.yaml`, valor fixo) | Timeout de execução de SQL em segundos (`30`). |
| `CHAINLIT_AUTH_SECRET` | Render (`sync: false`, manual) | Segredo usado pelo Chainlit para assinar a sessão de login (gerado via `chainlit create-secret`). |
| `APP_USERNAME` | Render (`sync: false`, manual) | Usuário do login único compartilhado do chat. |
| `APP_PASSWORD` | Render (`sync: false`, manual) | Senha do login único compartilhado do chat. |

---

## 8. Limitações conhecidas

- **Cold start do Render:** após 15 minutos de inatividade o backend "dorme"; a primeira requisição seguinte leva até ~1 minuto para responder.
- **Sessões de chat em memória:** o histórico de conversa é mantido em memória do processo (`memory.py`); qualquer reinício do backend (deploy novo ou saída do cold start) zera as sessões ativas.
- **Login único compartilhado:** não há contas individuais por analista nem OAuth — todo o time usa o mesmo usuário/senha (`APP_USERNAME`/`APP_PASSWORD`). Suficiente para fechar o acesso público, mas sem auditoria por pessoa.
- **Sem CI/testes automatizados antes do deploy:** não há pipeline que rode testes antes de publicar mudanças na `master`; validação hoje é manual, via o smoke test da seção 6. Candidata a próxima feature.

---

## 9. Troubleshooting

**`/catalog` retorna vazio ou erro no backend**
Confira se o build do Render usou `dockerContext: .` (raiz do repositório) e não `backend/`. Sem isso, `COPY catalog ./catalog` no `backend/Dockerfile` não encontra a pasta `catalog/`, e `CATALOG_PATH=/app/catalog/metrics.yaml` fica vazio.

**Erro 401 ao chamar a LLM**
Confira o valor de `ANTHROPIC_API_KEY` no dashboard do Render (Environment). Como essa variável é `sync: false`, ela não vem do `render.yaml` e precisa ser preenchida manualmente após a criação do serviço.

**Backend não sobe: `ValueError: You must provide a JWT secret...`**
`CHAINLIT_AUTH_SECRET` não foi preenchida no Render. Gere um valor com `chainlit create-secret` e configure em Environment antes de reiniciar o serviço.

**Login não aceita as credenciais**
Confira `APP_USERNAME`/`APP_PASSWORD` no dashboard do Render. Os dois precisam estar preenchidos — se qualquer um estiver vazio, o login é sempre rejeitado (ver `auth_callback` em `backend/app/chainlit_app.py`).

**A UI não abre em `https://<nome-do-servico>.onrender.com/`**
A UI do Chainlit fica montada em `/chainlit`, não na raiz do serviço — acesse `https://<nome-do-servico>.onrender.com/chainlit`. A raiz e outras rotas fora desse caminho não servem a interface de chat.

**Login local retorna 500 (`docker compose`), variáveis viram vazias em `docker compose ps`**
O valor gerado por `chainlit create-secret` pode conter caracteres especiais de shell (`$`, `%`, `=`, `>`, `:`, `*`). O parser de `.env` do Docker Compose interpreta `$algo` como referência a outra variável e substitui por vazio — corrompendo o segredo silenciosamente (aparecem avisos tipo `The "xyz" variable is not set` ao rodar `docker compose ps`/`up`). Gere um segredo sem caracteres especiais, por exemplo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Depois de trocar o valor em `.env`, recrie o container para ele pegar o novo valor: `docker compose up -d --force-recreate backend`.
