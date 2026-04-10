from typing import Literal, TypeAlias, NewType

AgentID: TypeAlias = Literal["agent_a", "agent_b", "dungeon_master"]

Position: TypeAlias = tuple[int, int]

CellType: TypeAlias = Literal["floor", "wall", "key", "locked_door", "exit", "agent"]

Direction: TypeAlias = Literal["north", "south", "east", "west"]

TurnNumber = NewType("TurnNumber", int)

RunID = NewType("RunID", str)

ToolName: TypeAlias = Literal["move", "observe", "interact", "communicate"]

TerminationReason: TypeAlias = Literal["win", "turn_limit", "stuck"]
