"""M-05 — Environment: Interaction & Action Validation.

This module is the physics engine of the dungeon.  No mutation to game state
may happen without first passing through ``InteractionValidator``.
"""
from __future__ import annotations

from packages.shared.types import AgentID, Direction, Position

from .grid import DungeonGrid

# Direction vectors in (row, col) order
_DIRECTION_DELTAS: dict[Direction, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "east": (0, 1),
    "west": (0, -1),
}

# Cell types that a moving agent may enter
_PASSABLE_CELL_TYPES = frozenset({"floor", "key", "exit"})


class InteractionValidator:
    """Validates every agent action before it is applied to the dungeon.

    All methods are stateless with respect to this object; all required state
    is passed in as arguments so the validator can be used as a pure function
    layer.
    """

    # ------------------------------------------------------------------
    # Move validation
    # ------------------------------------------------------------------

    def validate_move(
        self,
        agent_id: AgentID,
        direction: Direction,
        current_pos: Position,
        grid: DungeonGrid,
        door_unlocked: bool,
    ) -> tuple[bool, str, Position | None]:
        """Validate an agent move in *direction* from *current_pos*.

        Returns:
            ``(is_valid, reason_message, new_position_if_valid)``

        Rules
        -----
        - Invalid if the target cell is out-of-bounds.
        - Invalid if the target cell is a wall.
        - Invalid if the target cell is ``locked_door`` and *door_unlocked* is
          ``False``.
        - Valid for floor, key, exit, and unlocked door.
        """
        dr, dc = _DIRECTION_DELTAS[direction]
        row, col = current_pos
        new_pos: Position = (row + dr, col + dc)

        # Bounds check (grid raises IndexError if out of bounds)
        try:
            cell = grid.get_cell(new_pos)
        except IndexError:
            return (
                False,
                f"Agent {agent_id} cannot move {direction}: target {new_pos} is out of bounds.",
                None,
            )

        cell_type = cell.cell_type

        if cell_type == "wall":
            return (
                False,
                f"Agent {agent_id} cannot move {direction}: target cell {new_pos} is a wall.",
                None,
            )

        if cell_type == "locked_door":
            if not door_unlocked:
                return (
                    False,
                    f"Agent {agent_id} cannot move {direction}: the door at {new_pos} is locked.",
                    None,
                )
            # Door is unlocked — treat as passable
            return (
                True,
                f"Agent {agent_id} moves {direction} through the unlocked door to {new_pos}.",
                new_pos,
            )

        if cell_type in _PASSABLE_CELL_TYPES:
            return (
                True,
                f"Agent {agent_id} moves {direction} to {new_pos} ({cell_type}).",
                new_pos,
            )

        # Catch-all for any future cell types not yet handled
        return (
            False,
            f"Agent {agent_id} cannot move {direction}: target cell type '{cell_type}' is not passable.",
            None,
        )

    # ------------------------------------------------------------------
    # Interact validation
    # ------------------------------------------------------------------

    def validate_interact(
        self,
        agent_id: AgentID,
        current_pos: Position,
        grid: DungeonGrid,
        key_held_by: AgentID | None,
        door_unlocked: bool,
    ) -> tuple[bool, str, dict]:
        """Validate an agent interaction at *current_pos*.

        Two sub-actions are handled:

        **Pick up key**
            Valid only if the agent is standing on the ``key`` cell and no
            other agent already holds the key.

        **Unlock door**
            Valid only if the agent holds the key and is *adjacent* (one step
            in any cardinal direction) to a ``locked_door`` cell, and the door
            has not already been unlocked.

        Returns:
            ``(is_valid, reason_message, state_mutations_dict)``

            *state_mutations_dict* describes what state changes should be
            applied when valid:

            - Key pick-up: ``{"key_held_by": agent_id}``
            - Door unlock: ``{"door_unlocked": True}``
            - When invalid: ``{}``
        """
        try:
            current_cell = grid.get_cell(current_pos)
        except IndexError:
            return (
                False,
                f"Agent {agent_id} interact failed: position {current_pos} is out of bounds.",
                {},
            )

        # --- Pick up key -----------------------------------------------
        if current_cell.cell_type == "key":
            if key_held_by is not None:
                return (
                    False,
                    f"Agent {agent_id} cannot pick up the key: it is already held by {key_held_by}.",
                    {},
                )
            return (
                True,
                f"Agent {agent_id} picks up the key at {current_pos}.",
                {"key_held_by": agent_id},
            )

        # --- Unlock door ------------------------------------------------
        # The agent must hold the key and be adjacent to a locked_door.
        adjacent_door_pos = self._adjacent_locked_door(current_pos, grid)
        if adjacent_door_pos is not None:
            if key_held_by != agent_id:
                return (
                    False,
                    f"Agent {agent_id} cannot unlock the door at {adjacent_door_pos}: agent does not hold the key.",
                    {},
                )
            if door_unlocked:
                return (
                    False,
                    f"Agent {agent_id} cannot unlock the door at {adjacent_door_pos}: it is already unlocked.",
                    {},
                )
            return (
                True,
                f"Agent {agent_id} unlocks the door at {adjacent_door_pos}.",
                {"door_unlocked": True},
            )

        # --- Nothing to interact with -----------------------------------
        return (
            False,
            (
                f"Agent {agent_id} has nothing to interact with at {current_pos}: "
                "not standing on key, not adjacent to a locked door."
            ),
            {},
        )

    # ------------------------------------------------------------------
    # Observe validation
    # ------------------------------------------------------------------

    def validate_observe(
        self,
        agent_id: AgentID,
        position: Position,
        grid: DungeonGrid,
    ) -> tuple[bool, str]:
        """Validate an observe action.

        Observing is always valid — it produces no mutation.

        Returns:
            ``(True, reason_message)`` unconditionally.
        """
        return (
            True,
            f"Agent {agent_id} observes surroundings at {position}.",
        )

    # ------------------------------------------------------------------
    # Communicate validation
    # ------------------------------------------------------------------

    def validate_communicate(
        self,
        sender: AgentID,
        recipient: AgentID,
        content: str,
    ) -> tuple[bool, str]:
        """Validate a communicate action.

        Invalid if *sender* equals *recipient* or if *content* is empty.

        Returns:
            ``(is_valid, reason_message)``
        """
        if sender == recipient:
            return (
                False,
                f"Agent {sender} cannot send a message to itself.",
            )
        if not content or not content.strip():
            return (
                False,
                f"Agent {sender} cannot send an empty message to {recipient}.",
            )
        return (
            True,
            f"Agent {sender} sends a message to {recipient}.",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _adjacent_locked_door(
        self,
        pos: Position,
        grid: DungeonGrid,
    ) -> Position | None:
        """Return the position of an adjacent ``locked_door`` cell, or None."""
        row, col = pos
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor: Position = (row + dr, col + dc)
            try:
                cell = grid.get_cell(neighbor)
            except IndexError:
                continue
            if cell.cell_type == "locked_door":
                return neighbor
        return None
