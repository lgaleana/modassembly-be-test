from abc import ABC
from typing import Generic, List, TypeVar, get_args

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ValidationError

from ai import llm
from ai.llm import RawFunctionParams
from utils.state import Conversation
from utils.io import print_system


class WrongFunctionOutput(Exception):
    pass


Parameters = TypeVar("Parameters", bound=BaseModel)


class Function(ABC, Generic[Parameters]):
    description: str

    def __init__(self, *, id: str, name: str, parameters: Parameters):
        self.id = id
        self.name = name
        self.parameters = parameters

    @classmethod
    def parameters_schema(cls) -> Parameters:
        return get_args(cls.__orig_bases__[0])[0]  # type: ignore

    @classmethod
    def tool(cls) -> ChatCompletionToolParam:
        return ChatCompletionToolParam(
            function=FunctionDefinition(
                name=cls.__name__,
                description=cls.description,
                parameters=cls.parameters_schema().schema(),
            ),
            type="function",
        )

    @classmethod
    def parse_arguments(cls, raw_function: RawFunctionParams) -> List[Parameters]:
        param_schema = cls.parameters_schema()

        param_objects = []
        for argument in raw_function.arguments:
            parameters = param_schema.model_validate(argument)
            param_objects.append(
                cls(
                    id=raw_function.id,
                    name=raw_function.name,
                    parameters=parameters,
                ).parameters
            )
        return param_objects

    @classmethod
    def execute(cls, conversation: Conversation, max_tries: int = 2) -> List[Parameters]:
        tries = 1
        while tries <= max_tries:
            generation = llm.stream_next(conversation, tools=[cls.tool()])
            print_system(generation)
            if isinstance(generation, RawFunctionParams):
                conversation.add_raw_tool(generation)
                try:
                    return cls.parse_arguments(generation)
                except ValidationError as e:
                    print_system(e)
                    conversation.add_tool_response(str(e))
            conversation.add_user(
                f"Wrong output. Correct output :: {cls.parameters_schema()}"
            )
            tries += 1
        raise WrongFunctionOutput(f"Wrong output for {cls}")

    @classmethod
    def parse_multi_tool(cls, raw_function: RawFunctionParams) -> RawFunctionParams:
        return RawFunctionParams(
            id=raw_function.id,
            name=cls.__name__,
            arguments=[a["parameters"] for a in raw_function.arguments[0]["tool_uses"]],
        )
