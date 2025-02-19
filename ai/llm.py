from typing import Any, Dict, Iterator, List, Literal, Optional, Union, Tuple

import json
from pydantic import BaseModel
from openai import OpenAI, Stream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.completion_usage import CompletionUsage

from utils.io import print_assistant, print_system


client = OpenAI()


MODEL = "o3-mini-2025-01-31"
TEMPERATURE = 0.0


class RawFunctionParams(BaseModel):
    id: str
    name: str
    arguments: List[Dict[str, Any]]

    def __str__(self) -> str:
        return json.dumps(self.dict(), indent=2)


def _generate(
    messages,  # PITA to type this
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: List[ChatCompletionToolParam] = [],
    reasoning_effort: Literal["low", "medium", "high"] = "low",
) -> Stream[ChatCompletionChunk]:
    if not model:
        model = MODEL
    if temperature is None:
        temperature = TEMPERATURE

    cleaned_messages = []
    for message in messages:
        cleaned_messages.append(
            {"role": message["role"], "content": message["content"]}
        )

    if tools:
        return client.chat.completions.create(
            model=model,
            messages=cleaned_messages,
            stream=True,
            tools=tools,
            tool_choice="auto",
            reasoning_effort=reasoning_effort,
        )
    return client.chat.completions.create(
        model=model,
        messages=cleaned_messages,
        stream=True,
        reasoning_effort=reasoning_effort,
    )


def stream_next(
    messages,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: List[ChatCompletionToolParam] = [],
) -> Union[str, RawFunctionParams]:
    response = _generate(messages, model, temperature, tools)

    first_chunk = next(response)
    while (
        first_chunk.choices[0].delta.content is None
        and first_chunk.choices[0].delta.tool_calls is None
    ):
        first_chunk = next(response)

    if first_chunk.choices[0].delta.content is not None:
        output = "".join(_collect_text(first_chunk, response))
    else:
        output, usage = _collect_tool(first_chunk, response)

    return output


def stream_text(
    messages,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Literal["low", "medium", "high"] = "low",
) -> str:
    response = _generate(messages, model, temperature, tools=[])

    first_chunk = next(response)
    while (
        first_chunk.choices[0].delta.content is None
        and first_chunk.choices[0].delta.tool_calls is None
    ):
        first_chunk = next(response)

    assert first_chunk.choices[0].delta.content is not None

    output = "".join(_collect_text(first_chunk, response))
    return output


def stream_function(
    messages,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: List[ChatCompletionToolParam] = [],
) -> RawFunctionParams:
    assert len(tools) > 0
    response = _generate(messages, model, temperature, tools)

    first_chunk = next(response)
    while (
        first_chunk.choices[0].delta.content is None
        and first_chunk.choices[0].delta.tool_calls is None
    ):
        first_chunk = next(response)

    assert first_chunk.choices[0].delta.content is None

    output, usage = _collect_tool(first_chunk, response)
    return output


def stream(
    message: str, model: Optional[str] = None, temperature: Optional[float] = None
) -> str:
    messages = [{"role": "user", "content": message}]
    return stream_text(messages, model, temperature)


def iterate_text(
    messages,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Iterator[str]:
    response = _generate(messages, model, temperature, tools=[])

    first_chunk = next(response)
    while (
        first_chunk.choices[0].delta.content is None
        and first_chunk.choices[0].delta.tool_calls is None
    ):
        first_chunk = next(response)

    assert first_chunk.choices[0].delta.content is not None
    return _collect_text(first_chunk, response)


def _collect_text(
    first_chunk: ChatCompletionChunk, chunks: Stream[ChatCompletionChunk]
) -> Iterator[str]:
    yield first_chunk.choices[0].delta.content or ""
    print_assistant(first_chunk.choices[0].delta.content or "", end="", flush=True)
    for chunk in chunks:
        if chunk.choices and chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content
            print_assistant(chunk.choices[0].delta.content, end="", flush=True)
    print_assistant()


def _collect_tool(
    first_chunk: ChatCompletionChunk, chunks: Stream[ChatCompletionChunk]
) -> Tuple[RawFunctionParams, CompletionUsage]:
    assert first_chunk.choices[0].delta.tool_calls
    assert first_chunk.choices[0].delta.tool_calls[0].id
    assert first_chunk.choices[0].delta.tool_calls[0].function
    assert first_chunk.choices[0].delta.tool_calls[0].function.name
    tool_id = first_chunk.choices[0].delta.tool_calls[0].id
    tool_name = first_chunk.choices[0].delta.tool_calls[0].function.name
    usage = None

    arguments = first_chunk.choices[0].delta.tool_calls[0].function.arguments or ""
    print_assistant(".", end="", flush=True)
    arguments_list = []
    current_index = 0
    for chunk in chunks:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.tool_calls:
            if chunk.choices[0].delta.tool_calls[0].index != current_index:
                arguments = _parse_args(arguments)
                arguments_list.append(arguments)
                current_index = chunk.choices[0].delta.tool_calls[0].index
                arguments = ""
            if chunk.choices[0].delta.tool_calls[0].function:
                arguments += (
                    chunk.choices[0].delta.tool_calls[0].function.arguments or ""
                )
        print_assistant(".", end="", flush=True)
    arguments = _parse_args(arguments)
    arguments_list.append(arguments)
    print_assistant()

    assert usage
    return (
        RawFunctionParams(id=tool_id, name=tool_name, arguments=arguments_list),
        usage,
    )


def _parse_args(args: str) -> Dict[str, Any]:
    escaped_args = _escape_quotes(args)
    try:
        escaped_args = json.loads(escaped_args)
    except json.JSONDecodeError as e:
        print_system(args)
        breakpoint()
        raise e
    return _unesacape_quotes(escaped_args)


def _escape_quotes(val: str) -> str:
    return val.replace(r"\\'", "<ESCAPED_QUOTE>").replace(r"\'", "<ESCAPED_QUOTE>")


def _unesacape_quotes(val: Any) -> Any:
    if isinstance(val, str):
        return val.replace("<ESCAPED_QUOTE>", "\\'")
    if isinstance(val, List):
        return [_unesacape_quotes(v) for v in val]
    if isinstance(val, Dict):
        return {k: _unesacape_quotes(v) for k, v in val.items()}
    return val
