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
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.agent.fabric_mcp import fabric_mcp_tools
from app.agent.fabric_tools import FABRIC_LOCAL_TOOLS, triage_fabric_scope
from app.agent.memory import append_message, get_history
from app.agent.prompts import (
    FABRIC_OUT_OF_SCOPE_ANSWER,
    FABRIC_SYSTEM_PROMPT,
    FABRIC_TRIAGE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TRIAGE_SYSTEM_PROMPT,
)
from app.agent.tools import ALL_TOOLS, generate_chart, triage_scope

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


def _parse_tool_payload(result: Any) -> Any:
    """Normalize a tool result, decoding JSON strings returned by MCP tools."""
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (ValueError, TypeError):
            return result
    return result


def _extract_dax_rows(payload: Any) -> list[dict] | None:
    """Flatten a Fabric executeQueries payload (results[0].tables[0].rows) into row dicts."""
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), list):
        return payload["data"]
    try:
        rows = payload["results"][0]["tables"][0]["rows"]
    except (KeyError, IndexError, TypeError):
        return None
    return rows if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None


def _extract_final_answer(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content
    return "Não consegui formular uma resposta completa."


async def run_agent(
    user_message: str,
    session_id: str,
    domain: str = "ar",
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Run a bounded ReAct loop for the requested domain.
    Returns a structured dict ready for the API response.
    """
    if domain == "fabric":
        start = time.time()
        try:
            async with fabric_mcp_tools() as mcp_tools:
                tools = [*mcp_tools, *FABRIC_LOCAL_TOOLS, generate_chart]
                return await _run_react_loop(
                    user_message,
                    session_id,
                    tools,
                    system_prompt=FABRIC_SYSTEM_PROMPT,
                    triage_prompt=FABRIC_TRIAGE_SYSTEM_PROMPT,
                    triage_tool=triage_fabric_scope,
                    out_of_scope_answer=FABRIC_OUT_OF_SCOPE_ANSWER,
                    config=config,
                )
        except Exception as e:
            logger.exception("Failed to connect to the Fabric MCP server")
            return {
                "answer": (
                    "Não consegui conectar ao servidor Fabric (MCP) agora. "
                    "Isso costuma acontecer quando o serviço MCP remoto está fora do ar "
                    "ou o token de autenticação (MCP_AUTH_TOKEN) não está configurado "
                    f"corretamente no backend. Detalhe técnico: {e}"
                ),
                "data": None,
                "chart_spec": None,
                "lineage": None,
                "final_sql": None,
                "tools_called": [],
                "plan": None,
                "steps": ["mcp:connection_failed"],
                "latency_ms": int((time.time() - start) * 1000),
            }

    return await _run_react_loop(
        user_message,
        session_id,
        ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        triage_prompt=TRIAGE_SYSTEM_PROMPT,
        triage_tool=triage_scope,
        out_of_scope_answer=OUT_OF_SCOPE_ANSWER,
        config=config,
    )


async def _run_react_loop(
    user_message: str,
    session_id: str,
    tools: list[BaseTool],
    *,
    system_prompt: str,
    triage_prompt: str,
    triage_tool: BaseTool,
    out_of_scope_answer: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Run a bounded ReAct loop with the given prompts and tool set.
    Returns a structured dict ready for the API response.
    """
    start = time.time()
    llm = _build_llm()
    history = get_history(session_id)
    steps: list[str] = []

    if LLM_PROVIDER in TOOL_CHOICE_FORCING_PROVIDERS:
        triage_messages: list = [SystemMessage(content=triage_prompt)]
        for h in history[-2:]:
            role = HumanMessage if h["role"] == "user" else AIMessage
            triage_messages.append(role(content=h["content"]))
        triage_messages.append(HumanMessage(content=user_message))

        try:
            triage_llm = llm.bind_tools([triage_tool], tool_choice=triage_tool.name)
            triage_response: AIMessage = await triage_llm.ainvoke(triage_messages, config=config)
            if triage_response.tool_calls:
                triage_args = triage_response.tool_calls[0]["args"]
                if not triage_args.get("in_scope", True):
                    reason = (triage_args.get("reason") or "").strip()
                    reason_clause = f" e não posso ajudar com esse assunto ({reason})" if reason else ""
                    answer = out_of_scope_answer.format(reason_clause=reason_clause)
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

    llm_with_tools = llm.bind_tools(tools)
    tools_by_name = {t.name: t for t in tools}

    messages: list = [SystemMessage(content=system_prompt)]

    for h in history[-6:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))

    messages.append(HumanMessage(content=user_message))
    append_message(session_id, "user", user_message)

    tools_called: list[dict] = []
    seen_tool_calls: dict[tuple[str, str], Any] = {}
    final_sql: str | None = None
    data: list[dict] | None = None
    chart_spec: dict | None = None
    lineage: dict | None = None
    plan: str | None = None
    answer: str = "Não foi possível gerar uma resposta."

    repeat_counts: dict[tuple[str, str], int] = {}
    loop_completed_normally = False
    loop_detected = False

    for step in range(MAX_STEPS):
        steps.append(f"step_{step + 1}")
        try:
            response: AIMessage = await llm_with_tools.ainvoke(messages, config=config)
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
            partial_note = (
                " Alguns dados já haviam sido obtidos antes da falha; veja data/chart_spec/lineage."
                if any(v is not None for v in (data, chart_spec, lineage))
                else ""
            )
            return {
                "answer": f"Erro ao chamar o modelo ({LLM_PROVIDER}): {e}.{hint}{partial_note}",
                "data": data,
                "chart_spec": chart_spec,
                "lineage": lineage,
                "final_sql": final_sql,
                "tools_called": tools_called,
                "plan": plan,
                "steps": steps,
                "latency_ms": int((time.time() - start) * 1000),
            }

        messages.append(response)

        if not response.tool_calls:
            answer = response.content or "Sem conteúdo."
            append_message(session_id, "assistant", answer)
            loop_completed_normally = True
            break

        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool_id = tc.get("id", name)
            steps.append(f"tool:{name}")
            tools_called.append({"name": name, "args": args})

            call_key = (name, json.dumps(args, default=str, sort_keys=True))
            is_duplicate_call = call_key in seen_tool_calls
            repeat_counts[call_key] = repeat_counts.get(call_key, 0) + 1
            if repeat_counts[call_key] > 2:
                loop_detected = True

            if is_duplicate_call:
                result = seen_tool_calls[call_key]
                logger.warning(
                    "Duplicate tool call detected, reusing cached result: %s(%s)",
                    name,
                    json.dumps(args, default=str)[:200],
                )
            else:
                logger.info("Tool call: %s(%s)", name, json.dumps(args, default=str)[:200])
                tool_fn = tools_by_name.get(name)
                if not tool_fn:
                    result: Any = {"error": f"Tool desconhecida: {name}"}
                else:
                    try:
                        result = await tool_fn.ainvoke(args)
                    except Exception as e:
                        result = {"error": str(e)}
                seen_tool_calls[call_key] = result

            if name == "execute_sql" and isinstance(result, dict):
                if result.get("sql_executed"):
                    final_sql = result["sql_executed"]
                if result.get("data") is not None:
                    data = result["data"]
            if name == "execute_dax_query":
                payload = _parse_tool_payload(result)
                final_sql = args.get("dax_code") or final_sql
                data = _extract_dax_rows(payload) or data
            if name == "generate_chart" and isinstance(result, dict) and "chart_type" in result:
                chart_spec = result
            if name in ("get_lineage", "get_fabric_lineage") and isinstance(result, dict):
                lineage = result
            if (
                name
                in (
                    "list_metrics",
                    "get_metric_definition",
                    "list_fabric_measures",
                    "get_fabric_measure_definition",
                )
                and plan is None
            ):
                plan = f"Consultou catálogo via {name}"

            message_payload = _parse_tool_payload(result)
            if is_duplicate_call:
                message_payload = {
                    "note": (
                        "Esta tool já foi chamada antes nesta mesma conversa com exatamente "
                        "os mesmos argumentos — o resultado abaixo é reaproveitado do cache, "
                        "a chamada não foi repetida. Não chame esta tool de novo com os mesmos "
                        "argumentos; use o resultado abaixo para responder ao usuário agora."
                    ),
                    "cached_result": message_payload,
                }
            messages.append(
                ToolMessage(
                    content=json.dumps(message_payload, default=str, ensure_ascii=False),
                    tool_call_id=tool_id,
                )
            )
            if loop_detected:
                logger.warning(
                    "Tool call loop detected (%s repeated), ending turn early", call_key[0]
                )
                break

        if loop_detected:
            break

    if not loop_completed_normally:
        # Max steps reached, or a repeated tool-call loop was detected early
        answer = _extract_final_answer(messages)
        answer += "\n\n_(Limite de passos do agente atingido.)_"
        append_message(session_id, "assistant", answer)

    latency_ms = int((time.time() - start) * 1000)

    # Ensure lineage exists even if the model forgot to call the tool
    if triage_tool is triage_scope and lineage is None and final_sql:
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
