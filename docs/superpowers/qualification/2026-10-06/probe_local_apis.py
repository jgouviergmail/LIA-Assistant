"""Read-only inference qualification; run inside LIA's API Docker runtime.

Only synthetic prompts and a disposable local model are used. This is evidence
collection, not an implementation of the proposed application providers.
"""

import argparse
import asyncio
import importlib.metadata
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["probe"]
    value: int


class NestedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: int | None


class NestedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["probe"]
    items: list[NestedItem]


TOOL = {
    "type": "function",
    "function": {
        "name": "echo_marker",
        "description": "Return the marker supplied by the caller.",
        "parameters": {
            "type": "object",
            "properties": {"marker": {"type": "string", "enum": ["probe"]}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    },
}
TOOL_PROMPT = "Call echo_marker with marker probe. Do not answer directly. /no_think"
TEXT_PROMPT = "Output only the literal string probe. /no_think"


async def run(args):
    records = []
    base = args.base.rstrip("/")
    headers = {"Authorization": "Bearer lia-qualification-key"}
    metadata = {
        "utc": datetime.now(UTC).isoformat(),
        "provider": args.kind,
        "base": base,
        "model": args.model,
        "libraries": {
            name: importlib.metadata.version(name)
            for name in ("httpx", "openai", "langchain-openai", "langchain-core", "pydantic")
        },
    }

    async with httpx.AsyncClient(timeout=90, headers=headers) as client:

        async def case(name, operation):
            started = time.monotonic()
            observation = {}
            try:
                await operation(observation)
                passed, error = True, None
            except Exception as exc:
                passed, error = False, f"{type(exc).__name__}: {exc}"[:1800]
            record = {
                "case": name,
                "passed": passed,
                "error": error,
                "seconds": round(time.monotonic() - started, 3),
                "observation": observation,
            }
            records.append(record)
            print(
                json.dumps({k: record[k] for k in ("case", "passed", "error", "seconds")}),
                flush=True,
            )
            Path(args.output).write_text(
                json.dumps({"metadata": metadata, "cases": records}, indent=2), encoding="utf-8"
            )

        def payload(messages=None, **extras):
            return {
                "model": args.model,
                "messages": messages or [{"role": "user", "content": TEXT_PROMPT}],
                "temperature": 0,
                "max_tokens": 160,
                **extras,
            }

        async def post(body, observation):
            observation["request"] = body
            response = await client.post(base + "/v1/chat/completions", json=body)
            observation["http_status"] = response.status_code
            try:
                data = response.json()
            except ValueError:
                data = {"raw": response.text[:1800]}
            observation["response"] = data
            response.raise_for_status()
            return data

        async def discovery(o):
            r = await client.get(base + "/v1/models")
            o["http_status"], o["response"] = r.status_code, r.json()
            r.raise_for_status()
            assert args.model in [m["id"] for m in r.json()["data"]]
            route = "/props" if args.kind == "llamacpp" else "/api/v1/models"
            if args.kind == "ollama":
                r = await client.post(base + "/api/show", json={"model": args.model})
            else:
                r = await client.get(base + route)
            o["native_metadata_status"], o["native_metadata"] = r.status_code, r.json()
            r.raise_for_status()

        async def text(o):
            data = await post(payload(), o)
            assert "probe" in (data["choices"][0]["message"].get("content") or "").lower()
            assert data["usage"]["prompt_tokens"] > 0
            assert data["usage"]["completion_tokens"] > 0

        async def structured(o, schema, expected):
            body = payload(
                messages=[
                    {
                        "role": "user",
                        "content": f"Return JSON only: {json.dumps(expected)}. /no_think",
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
            data = await post(body, o)
            value = schema.model_validate_json(data["choices"][0]["message"]["content"])
            assert value.model_dump() == expected

        async def parameter_schema(o):
            from src.domains.agents.orchestration.plan_schemas import ParameterItem

            await structured(
                o,
                ParameterItem,
                {
                    "name": "marker",
                    "value": {"string_value": "probe", "value_type": "string"},
                },
            )

        async def stream(o, tools=False, reasoning=False, choice=None):
            body = payload(stream=True, stream_options={"include_usage": True})
            if tools:
                body.update(
                    tools=[TOOL],
                    tool_choice=choice or {"type": "function", "function": {"name": "echo_marker"}},
                )
                body["messages"] = [{"role": "user", "content": TOOL_PROMPT}]
            if reasoning:
                body["messages"] = [
                    {"role": "user", "content": "What is 17 times 19? Think briefly. /think"}
                ]
                body["max_tokens"] = 192
                if args.kind == "llamacpp":
                    body["chat_template_kwargs"] = {"enable_thinking": True}
                elif args.kind == "ollama":
                    body["think"] = True
            o["request"], events, done = body, [], False
            async with client.stream("POST", base + "/v1/chat/completions", json=body) as response:
                o["http_status"] = response.status_code
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        done = True
                    elif raw:
                        events.append(json.loads(raw))
            o["events"], o["done"] = events, done
            assert done and events
            usage = [event["usage"] for event in events if event.get("usage")]
            assert usage and usage[-1]["prompt_tokens"] > 0
            if tools:
                fragments = [
                    call
                    for event in events
                    for choice in event.get("choices", [])
                    for call in choice.get("delta", {}).get("tool_calls", [])
                ]
                name = "".join(call.get("function", {}).get("name", "") for call in fragments)
                arguments = "".join(
                    call.get("function", {}).get("arguments", "") for call in fragments
                )
                assert name == "echo_marker" and json.loads(arguments) == {"marker": "probe"}
                assert any(call.get("id") for call in fragments)
            elif reasoning:
                o["reasoning_content_seen"] = any(
                    choice.get("delta", {}).get("reasoning_content")
                    for event in events
                    for choice in event.get("choices", [])
                )
            else:
                content = "".join(
                    choice.get("delta", {}).get("content") or ""
                    for event in events
                    for choice in event.get("choices", [])
                )
                assert "probe" in content.lower()

        async def tools(o, forced=False, choice=None):
            body = payload(messages=[{"role": "user", "content": TOOL_PROMPT}], tools=[TOOL])
            if forced:
                body["tool_choice"] = {"type": "function", "function": {"name": "echo_marker"}}
            if choice is not None:
                body["tool_choice"] = choice
            data = await post(body, o)
            message = data["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            assert len(calls) == 1 and calls[0].get("id")
            assert calls[0]["function"]["name"] == "echo_marker"
            assert json.loads(calls[0]["function"]["arguments"]) == {"marker": "probe"}
            follow = {
                "role": "tool",
                "tool_call_id": calls[0]["id"],
                "content": '{"marker":"probe","success":true}',
            }
            roundtrip = {}
            o["roundtrip"] = roundtrip
            final = await post(payload(messages=[*body["messages"], message, follow]), roundtrip)
            assert "probe" in (final["choices"][0]["message"].get("content") or "").lower()
            assert not final["choices"][0]["message"].get("tool_calls")

        async def negative(o, mode):
            body = payload()
            if mode == "unknown_model":
                body["model"] = "lia-qa-model-that-does-not-exist"
            else:
                body["messages"] = [{"role": "invalid-role", "content": {"malformed": True}}]
            r = await client.post(base + "/v1/chat/completions", json=body)
            o.update(request=body, http_status=r.status_code, response=r.json())
            assert r.status_code in (400, 404, 422)

        async def unauthorized(o):
            r = await client.get(
                base + "/v1/models", headers={"Authorization": "Bearer invalid-qualification-key"}
            )
            o.update(http_status=r.status_code, response=r.json())
            assert r.status_code in (401, 403)

        async def truncated(o):
            data = await post(
                payload(
                    messages=[
                        {"role": "user", "content": "Write twenty different words. /no_think"}
                    ],
                    max_tokens=1,
                ),
                o,
            )
            assert data["choices"][0]["finish_reason"] == "length"
            assert data["usage"]["completion_tokens"] <= 1

        async def cancel(o):
            body = payload(
                messages=[{"role": "user", "content": "Count from one to one hundred. /no_think"}],
                stream=True,
            )
            async with client.stream("POST", base + "/v1/chat/completions", json=body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line.startswith("data:") and line[5:].strip() != "[DONE]":
                        o["first_event"] = json.loads(line[5:])
                        break
            await text(o)

        def sdk():
            return ChatOpenAI(
                model=args.model,
                base_url=base + "/v1",
                api_key="lia-qualification-key",
                temperature=0,
                max_tokens=160,
                max_retries=0,
                timeout=90,
                use_responses_api=False,
            )

        async def sdk_text(o):
            llm = sdk()
            prompt = [HumanMessage(content=TEXT_PROMPT)]
            o["payload"] = llm._get_request_payload(prompt)
            message = await llm.ainvoke(prompt)
            o["message"] = message.model_dump(mode="json")
            assert "probe" in str(message.content).lower()
            assert message.usage_metadata and message.usage_metadata["input_tokens"] > 0

        async def sdk_schema(o):
            model = (
                await sdk()
                .with_structured_output(ProbeResult, method="json_schema", strict=True)
                .ainvoke('Return JSON only {"status":"probe","value":5}. /no_think')
            )
            o["value"] = model.model_dump()
            assert model == ProbeResult(status="probe", value=5)

        async def sdk_tools(o):
            message = await sdk().bind_tools([TOOL], tool_choice="echo_marker").ainvoke(TOOL_PROMPT)
            o["message"] = message.model_dump(mode="json")
            assert len(message.tool_calls) == 1
            assert message.tool_calls[0]["name"] == "echo_marker"
            assert message.tool_calls[0]["args"] == {"marker": "probe"}

        async def native_ollama(o):
            body = {
                "model": args.model,
                "messages": [{"role": "user", "content": 'Return {"status":"probe","value":5}.'}],
                "stream": False,
                "think": False,
                "format": ProbeResult.model_json_schema(),
                "options": {"num_ctx": 2048, "num_predict": 160, "temperature": 0},
            }
            r = await client.post(base + "/api/chat", json=body)
            o.update(request=body, http_status=r.status_code, response=r.json())
            r.raise_for_status()
            data = r.json()
            assert ProbeResult.model_validate_json(data["message"]["content"]) == ProbeResult(
                status="probe", value=5
            )
            assert data["prompt_eval_count"] > 0 and data["eval_count"] > 0
            from src.infrastructure.llm.providers.ollama_chat import ChatOllamaTraced

            native = ChatOllamaTraced(
                model=args.model,
                base_url=base,
                temperature=0,
                num_ctx=2048,
                num_predict=160,
                reasoning=False,
            )
            message = await native.ainvoke(TEXT_PROMPT)
            o["lia_native_message"] = message.model_dump(mode="json")
            assert "probe" in str(message.content).lower() and message.usage_metadata

        async def plan_schema(o):
            from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

            expected = {
                "plan_id": "probe",
                "user_id": "probe",
                "session_id": "probe",
                "steps": [],
                "metadata": {"needs_clarification": True},
            }
            body = payload(
                messages=[
                    {
                        "role": "user",
                        "content": f"Output exactly this JSON document: {json.dumps(expected)}. /no_think",
                    }
                ],
                max_tokens=320,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ExecutionPlan",
                        "strict": True,
                        "schema": ExecutionPlan.model_json_schema(),
                    },
                },
            )
            data = await post(body, o)
            assert data["choices"][0]["finish_reason"] != "length"
            value = ExecutionPlan.model_validate_json(data["choices"][0]["message"]["content"])
            assert (
                value.user_id == "probe"
                and not value.steps
                and value.metadata["needs_clarification"] is True
            )

        async def json_mode(o):
            data = await post(
                payload(
                    messages=[
                        {
                            "role": "user",
                            "content": 'Output only JSON {"status":"probe","value":5}. /no_think',
                        }
                    ],
                    response_format={"type": "json_object"},
                ),
                o,
            )
            assert ProbeResult.model_validate_json(
                data["choices"][0]["message"]["content"]
            ) == ProbeResult(status="probe", value=5)

        async def overflow(o):
            data = await client.post(
                base + "/v1/chat/completions",
                json=payload(
                    messages=[
                        {
                            "role": "user",
                            "content": "hello " * 3500 + "Output only probe. /no_think",
                        }
                    ],
                    max_tokens=8,
                ),
            )
            o.update(
                http_status=data.status_code,
                response=data.json(),
                input_repeated_words=3500,
                loaded_context=2048,
            )
            assert data.status_code in (
                400,
                422,
            ), "Server accepted input beyond the allocated context; inspect usage for truncation"

        async def parallel(o):
            observations = [{}, {}]
            responses = await asyncio.gather(
                *(post(payload(max_tokens=32), obs) for obs in observations)
            )
            o["calls"] = observations
            assert all(
                "probe" in r["choices"][0]["message"]["content"].lower()
                and r["usage"]["prompt_tokens"] > 0
                for r in responses
            )

        async def timeout(o):
            try:
                await client.post(
                    base + "/v1/chat/completions",
                    json=payload(
                        messages=[
                            {"role": "user", "content": "What is the sum of 456 and 987? /no_think"}
                        ],
                        max_tokens=8,
                    ),
                    timeout=httpx.Timeout(10, read=0.001),
                )
            except httpx.ReadTimeout:
                o["read_timeout_observed"] = True
            else:
                raise AssertionError(
                    "Probe completed before the read-timeout; timeout not qualified"
                )
            await text(o)

        async def sdk_required(o):
            message = await sdk().bind_tools([TOOL], tool_choice="required").ainvoke(TOOL_PROMPT)
            o["message"] = message.model_dump(mode="json")
            assert len(message.tool_calls) == 1 and message.tool_calls[0]["name"] == "echo_marker"
            assert message.tool_calls[0]["args"] == {"marker": "probe"}

        async def sdk_reasoning(o):
            extras = {}
            if args.kind == "llamacpp":
                extras["chat_template_kwargs"] = {"enable_thinking": True}
            elif args.kind == "ollama":
                extras["think"] = True
            llm = sdk().bind(extra_body=extras) if extras else sdk()
            messages = []
            async for message in llm.astream("What is 17 times 19? Think briefly. /think"):
                messages.append(message.model_dump(mode="json"))
            o["chunks"] = messages
            o["extra_body"] = extras
            assert any(
                m["additional_kwargs"].get("reasoning_content") for m in messages
            ), "No reasoning_content retained by installed ChatOpenAI; compare raw wire observation"

        if args.suite == "edge":
            await case("required_tool_and_result_roundtrip", lambda o: tools(o, choice="required"))
            await case(
                "streamed_required_tool_fragments",
                lambda o: stream(o, tools=True, choice="required"),
            )
            await case(
                "streamed_auto_tool_fragments", lambda o: stream(o, tools=True, choice="auto")
            )
            await case("installed_langchain_required_tools", sdk_required)
            await case("full_lia_execution_plan_schema", plan_schema)
            await case("json_object_mode", json_mode)
            await case("oversized_context_rejected", overflow)
            await case("two_concurrent_requests_one_server_slot", parallel)
            await case("read_timeout_then_next_request", timeout)
            await case("reasoning_preserved_by_installed_langchain", sdk_reasoning)
            print(
                json.dumps(
                    {
                        "provider": args.kind,
                        "suite": "edge",
                        "passed": sum(r["passed"] for r in records),
                        "total": len(records),
                    }
                ),
                flush=True,
            )
            return

        await case("discovery_and_runtime_metadata", discovery)
        await case("text_and_usage", text)
        await case(
            "strict_json_schema",
            lambda o: structured(o, ProbeResult, {"status": "probe", "value": 5}),
        )
        await case(
            "nested_refs_nullable_array_schema",
            lambda o: structured(
                o, NestedResult, {"status": "probe", "items": [{"name": "probe", "value": None}]}
            ),
        )
        await case("lia_parameter_item_schema", parameter_schema)
        await case("stream_and_final_usage", stream)
        await case("automatic_tool_and_result_roundtrip", tools)
        await case("forced_tool_and_result_roundtrip", lambda o: tools(o, forced=True))
        await case("streamed_forced_tool_fragments", lambda o: stream(o, tools=True))
        await case("output_budget_finish_reason", truncated)
        await case("unknown_model_rejected", lambda o: negative(o, "unknown_model"))
        await case("malformed_message_rejected", lambda o: negative(o, "malformed"))
        if args.kind == "llamacpp":
            await case("wrong_api_key_rejected", unauthorized)
        await case("cancel_stream_then_next_request", cancel)
        await case("installed_langchain_text_and_usage", sdk_text)
        await case("installed_langchain_json_schema", sdk_schema)
        await case("installed_langchain_forced_tools", sdk_tools)
        await case("reasoning_wire_observation", lambda o: stream(o, reasoning=True))
        if args.kind == "ollama":
            await case("native_ollama_and_existing_lia_client", native_ollama)

    print(
        json.dumps(
            {
                "provider": args.kind,
                "passed": sum(r["passed"] for r in records),
                "total": len(records),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("ollama", "llamacpp", "lmstudio"), required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--model", default="lia-qa-qwen3")
    parser.add_argument("--output", required=True)
    parser.add_argument("--suite", choices=("core", "edge"), default="core")
    asyncio.run(run(parser.parse_args()))
