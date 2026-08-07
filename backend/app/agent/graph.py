"""
GEFIN Agent core loop.

Pragmatic ReAct-style loop with LangChain tools.
Explicit control flow, easy to debug, perfect for a portfolio prototype.

Supported LLM providers:
  - anthropic  (Claude)  → recommended for quality
  - openai     (OpenAI or any OpenAI-compatible endpoint)
  - ollama     (fully local)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.memory import append_message, get_history
from app.agent.prompts import SYSTEM_PROMPT, TRIAGE_SYSTEM_PROMPT
from app.agent.tools import ALL_TOOLS, triage_scope

logger = logging.getLogger("gefin.agent")

MAX_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:14b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

# Providers whose LangChain integration supports forcing a specific tool via
# tool_choice. Ollama's support varies by model, so it falls back to the
# prompt-only guardrail in SYSTEM_PROMPT instead of a forced triage call.
TOOL_CHOICE_FORCING_PROVIDERS = {"anthropic", "openai"}

OUT_OF_SCOPE_ANSWER = (
    "Desculpe, mas sou especializado apenas em Contas a Receber{reason_clause}. "
    'Experimente perguntar, por exemplo: "Qual o saldo total em aberto?" ou '
    '"Mostre o aging por faixa de atraso".'
)


def _build_llm():
    """Build the chat model according to LLM_PROVIDER."""
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            temperature=0.1,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_tokens=4096,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )

    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )

    # Default: Ollama (local)
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def _extract_final_answer(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content
    return "Não consegui formular uma resposta completa."


async def run_agent(user_message: str, session_id: str) -> dict[str, Any]:
    """
    Run a bounded ReAct loop.
    Returns a structured dict ready for the API response.
    """
    start = time.time()
    llm = _build_llm()
    history = get_history(session_id)
    steps: list[str] = []

    if LLM_PROVIDER in TOOL_CHOICE_FORCING_PROVIDERS:
        triage_messages: list = [SystemMessage(content=TRIAGE_SYSTEM_PROMPT)]
        for h in history[-2:]:
            role = HumanMessage if h["role"] == "user" else AIMessage
            triage_messages.append(role(content=h["content"]))
        triage_messages.append(HumanMessage(content=user_message))

        try:
            triage_llm = llm.bind_tools([triage_scope], tool_choice="triage_scope")
            triage_response: AIMessage = await triage_llm.ainvoke(triage_messages)
            if triage_response.tool_calls:
                triage_args = triage_response.tool_calls[0]["args"]
                if not triage_args.get("in_scope", True):
                    reason = (triage_args.get("reason") or "").strip()
                    reason_clause = f" e não posso ajudar com esse assunto ({reason})" if reason else ""
                    answer = OUT_OF_SCOPE_ANSWER.format(reason_clause=reason_clause)
                    append_message(session_id, "user", user_message)
                    append_message(session_id, "assistant", answer)
                    return {
                        "answer": answer,
                        "steps": ["triage:out_of_scope"],
                        "latency_ms": int((time.time() - start) * 1000),
                    }
                steps.append("triage:in_scope")
        except Exception:
            logger.exception("Triage call failed; falling back to prompt-only guardrail")

    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    tools_by_name = {t.name: t for t in ALL_TOOLS}

    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

    for h in history[-6:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))

    messages.append(HumanMessage(content=user_message))
    append_message(session_id, "user", user_message)

    tools_called: list[dict] = []
    final_sql: str | None = None
    data: list[dict] | None = None
    chart_spec: dict | None = None
    lineage: dict | None = None
    plan: str | None = None
    answer: str = "Não foi possível gerar uma resposta."

    for step in range(MAX_STEPS):
        steps.append(f"step_{step + 1}")
        try:
            response: AIMessage = await llm_with_tools.ainvoke(messages)
        except Exception as e:
            logger.exception("LLM call failed")
            hint = ""
            if LLM_PROVIDER == "ollama":
                hint = (
                    f" Verifique se o Ollama está rodando e o modelo foi baixado "
                    f"(`docker compose exec ollama ollama pull {LLM_MODEL}`)."
                )
            elif LLM_PROVIDER == "anthropic":
                hint = " Verifique se ANTHROPIC_API_KEY está definida e é válida."
            elif LLM_PROVIDER == "openai":
                hint = " Verifique se OPENAI_API_KEY está definida e é válida."
            return {
                "answer": f"Erro ao chamar o modelo ({LLM_PROVIDER}): {e}.{hint}",
                "steps": steps,
                "latency_ms": int((time.time() - start) * 1000),
            }

        messages.append(response)

        if not response.tool_calls:
            answer = response.content or "Sem conteúdo."
            append_message(session_id, "assistant", answer)
            break

        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool_id = tc.get("id", name)
            steps.append(f"tool:{name}")
            tools_called.append({"name": name, "args": args})

            logger.info("Tool call: %s(%s)", name, json.dumps(args, default=str)[:200])

            tool_fn = tools_by_name.get(name)
            if not tool_fn:
                result: Any = {"error": f"Tool desconhecida: {name}"}
            else:
                try:
                    result = tool_fn.invoke(args)
                except Exception as e:
                    result = {"error": str(e)}

            if name == "execute_sql" and isinstance(result, dict):
                if result.get("sql_executed"):
                    final_sql = result["sql_executed"]
                if result.get("data") is not None:
                    data = result["data"]
            if name == "generate_chart" and isinstance(result, dict) and "chart_type" in result:
                chart_spec = result
            if name == "get_lineage" and isinstance(result, dict):
                lineage = result
            if name in ("list_metrics", "get_metric_definition") and plan is None:
                plan = f"Consultou catálogo via {name}"

            messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str, ensure_ascii=False),
                    tool_call_id=tool_id,
                )
            )
    else:
        # Max steps reached without a pure text response
        answer = _extract_final_answer(messages)
        answer += "\n\n_(Limite de passos do agente atingido.)_"
        append_message(session_id, "assistant", answer)

    latency_ms = int((time.time() - start) * 1000)

    # Ensure lineage exists even if the model forgot to call the tool
    if lineage is None and final_sql:
        from app.agent.tools import get_lineage as lineage_tool

        views = [
            v
            for v in [
                "vw_ar_open_items",
                "vw_ar_aging",
                "vw_ar_customer_summary",
                "vw_ar_kpi_daily",
                "vw_ar_dso",
            ]
            if v in (final_sql or "")
        ]
        lineage = lineage_tool.invoke(
            {"views_used": views or ["vw_ar_open_items"], "sql": final_sql}
        )

    return {
        "answer": answer,
        "data": data,
        "chart_spec": chart_spec,
        "lineage": lineage,
        "final_sql": final_sql,
        "tools_called": tools_called,
        "plan": plan,
        "steps": steps,
        "latency_ms": latency_ms,
    }
