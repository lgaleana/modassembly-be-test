from typing import Any, Dict, List, Optional, Union, Tuple

import json
from pydantic import BaseModel
from openai import OpenAI, Stream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.completion_usage import CompletionUsage

from utils.io import print_assistant, print_system


client = OpenAI()


MODEL = "gpt-4o"
TEMPERATURE = 0.0


class RawFunctionParams(BaseModel):
    id: str
    name: str
    arguments: List[Dict[str, Any]]

    def __str__(self) -> str:
        return json.dumps(self.dict(), indent=2)


class OCost(BaseModel):
    PRICE_PER_1K_INPUT: float = 0.005
    PRICE_PER_1K_OUTPUT: float = 0.015

    input: int = 0
    output: int = 0

    def get(self) -> float:
        return (
            self.PRICE_PER_1K_INPUT * self.input / 1_000
            + self.PRICE_PER_1K_OUTPUT * self.output / 1_000
        )


model_cost = OCost()


def _generate(
    messages,  # PITA to type this
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: List[ChatCompletionToolParam] = [],
) -> Stream[ChatCompletionChunk]:
    if not model:
        model = MODEL
    if temperature is None:
        temperature = TEMPERATURE

    if tools:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
            tools=tools,
            tool_choice="auto",
        )
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=True,
        stream_options={"include_usage": True},
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
        output, usage = _collect_text(first_chunk, response)
    else:
        output, usage = _collect_tool(first_chunk, response)

    return output


def stream_text(
    messages,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    response = _generate(messages, model, temperature, tools=[])

    first_chunk = next(response)
    while (
        first_chunk.choices[0].delta.content is None
        and first_chunk.choices[0].delta.tool_calls is None
    ):
        first_chunk = next(response)

    assert first_chunk.choices[0].delta.content is not None

    output, usage = _collect_text(first_chunk, response)
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


def _collect_text(
    first_chunk: ChatCompletionChunk, chunks: Stream[ChatCompletionChunk]
) -> Tuple[str, CompletionUsage]:
    message = first_chunk.choices[0].delta.content or ""
    usage = None
    print_assistant(message, end="", flush=True)
    for chunk in chunks:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content is not None:
            message += chunk.choices[0].delta.content
            print_assistant(chunk.choices[0].delta.content, end="", flush=True)
    print_assistant()
    assert usage
    return message, usage


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
