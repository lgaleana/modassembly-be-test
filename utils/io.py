from typing import Any


def print_system(message: Any = "", end: str = "\n") -> str:
    print(f"\033[0;0m{message}", end=end)
    return message


def print_assistant(message="", end: str = "\n", flush: bool = False) -> str:
    print(f"\033[92m{message}", end=end, flush=flush)
    return message


def user_input(message="") -> str:
    return input(f"\033[1;34m{message}")
