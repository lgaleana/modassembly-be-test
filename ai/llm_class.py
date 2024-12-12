from typing import Optional

from ai import llm as llm_module
from utils.state import Conversation
from utils.io import print_system,user_input


class LLM:
    def __init__(
        self, model: Optional[str] = None, temperature: Optional[float] = None
    ):
        self.model = model
        self.temperature = temperature
        self.conversation = Conversation()

    def add_system(self, message):
        self.conversation.add_system(str(message))

    def add_user(self, message):
        self.conversation.add_user(str(message))

    def add_assistant(self, message):
        self.conversation.add_assistant(str(message))

    def stream_text(self, user_message=None, *, preserve: bool = False) -> str:
        if user_message:
            self.add_user(user_message)

        text = llm_module.stream_text(self.conversation)
        self.add_assistant(text)

        if not preserve:
            self.conversation = Conversation()
        return text

    def chat(self, user_message=None, *, preserve: bool = False) -> None:
        if user_message:
            user_message = user_message
        else:
            user_message = user_input("user: ")

        while True:
            if user_message == "exit":
                break
            assert user_message is not None
            self.add_user(user_message)
            print_system(self.conversation.count_tokens())
            self.stream_text(preserve=True)
            user_message = user_input("user: ")

        if not preserve:
            self.conversation = Conversation()


llmc = LLM()
