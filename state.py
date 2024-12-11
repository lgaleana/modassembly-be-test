from datetime import datetime
import json
from copy import deepcopy
from typing import Any, Dict, List, Optional


from ai.tokens import count_tokens


class Conversation(List[Dict[str, Any]]):
    def add_assistant(self, message: str, *, type_: Optional[str] = None) -> None:
        if type_ is not None:
            self.append({"role": "assistant", "content": message, "type": type_})
        else:
            self.append({"role": "assistant", "content": message})

    def add_system(self, message: str, *, type_: Optional[str] = None) -> None:
        if type_ is not None:
            self.append({"role": "system", "content": message, "type": type_})
        else:
            self.append({"role": "system", "content": message})

    def add_user(self, message: str, *, type_: Optional[str] = None) -> None:
        if type_ is not None:
            self.append({"role": "user", "content": message, "type": type_})
        else:
            self.append({"role": "user", "content": message})

    def add_tool(self, tool) -> None:
        self.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool.id,
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "arguments": json.dumps(tool.parameters.dict(), indent=2),
                        },
                    }
                ],
                "content": None,
            }
        )

    def add_raw_tool(self, tool) -> None:
        self.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool.id,
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "arguments": json.dumps(tool.arguments, indent=2),
                        },
                    }
                ],
                "content": None,
            }
        )

    def add_tool_response(self, message: str) -> None:
        repective_tool_id = self[-1]["tool_calls"][0]["id"]
        self.append(
            {"role": "tool", "content": message, "tool_call_id": repective_tool_id}
        )

    def remove_last_message_type(self, type_: str) -> None:
        for i in range(len(self) - 1, -1, -1):
            if self[i].get("type") == type_:
                del self[i]
                break

    def copy(self) -> "Conversation":
        return deepcopy(self)

    def empty(self) -> bool:
        return len(self) == 0

    def persist(self, *, namespace: str, name: Optional[str] = None) -> None:
        if not getattr(self, "name", None):
            self.name = name or get_time_name()

        with open(f"db/{namespace}/{self.name}.json", "w") as file:
            json.dump(self, file, indent=4)

    def count_tokens(self) -> int:
        return sum(count_tokens(m["content"]) for m in self)

    @staticmethod
    def load(namespace: str, name: str) -> "Conversation":
        with open(f"db/{namespace}/{name}.json", "r") as file:
            payload = json.load(file)
        return Conversation(payload)


def get_time_name() -> str:
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
