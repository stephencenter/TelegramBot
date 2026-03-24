"""Dice utilities.

This module contains constants, classes, and functions used by Dice commands like
/roll, /statroll, and /d10000.
"""

import random
import re
from collections.abc import Callable
from dataclasses import dataclass

import common


def parse_diceroll(roll_string: str) -> tuple[int, int, int] | None:
    # Regex pattern that catches most diceroll formats, including "d6", "1d4", "2d8-2", and "3d2 + 3"
    dice_pattern = r'^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$'
    roll_args = re.match(dice_pattern, roll_string.strip().lower())

    if not roll_args:
        return None

    # Parse out the number of dice and faces and cast to int
    num_dice = int(roll_args.group(1)) if roll_args.group(1) else 1
    num_faces = int(roll_args.group(2))

    # Parse out the modifier. We split and re-join to remove any spaces, e.g. "- 2" -> "-2"
    modifier = int(''.join(roll_args.group(3).split())) if roll_args.group(3) else 0

    if num_dice < 1 or num_faces < 1:
        return None

    return num_dice, num_faces, modifier


async def get_d10000_roll(username: str) -> str:
    effects = await common.try_read_lines_list(common.PATH_D10000_LIST, None)
    if effects is None:
        return "The d10000 file couldn't be found!"

    active_effects = await common.try_read_json(common.PATH_ACTIVE_EFFECTS, {})

    try:
        effects = [x for x in effects if x not in active_effects[username]]
    except IndexError:
        active_effects[username] = []

    chosen_effect = random.choice(effects).strip()
    active_effects[username].append(chosen_effect)
    active_effects[username] = sorted(set(active_effects[username]))

    await common.write_json_to_file(common.PATH_ACTIVE_EFFECTS, active_effects)

    return chosen_effect


async def get_active_effects(username: str) -> list[str]:
    effects_dict = await common.try_read_json(common.PATH_ACTIVE_EFFECTS, {})

    try:
        active_effects = effects_dict[username]
    except KeyError:
        return []

    return active_effects


async def reset_active_effects(username: str) -> None:
    effects_dict = await common.try_read_json(common.PATH_ACTIVE_EFFECTS, {})
    effects_dict[username] = []

    await common.write_json_to_file(common.PATH_ACTIVE_EFFECTS, effects_dict)


@dataclass
class StatrollGame:
    """Dataclass for mapping TTRPG names to statroll functions."""

    game_name: str
    game_aliases: list[str]
    game_function: Callable[[], dict[str, int]]


def roll_dice(num_dice: int, num_sides: int, modifier: int) -> int:
    return sum(random.randint(1, num_dice) for _ in range(num_sides)) + modifier


def get_dnd_statroll() -> dict[str, int]:
    # Based on D&D 5e
    statroll: dict[str, int] = {
        "STR": 0,
        "DEX": 0,
        "CON": 0,
        "INT": 0,
        "WIS": 0,
        "CHA": 0,
    }

    # All ability scores use 4d6 drop lowest
    for stat in statroll:
        dice_rolls = [random.randint(1, 6) for _ in range(4)]
        statroll[stat] = sum(dice_rolls) - min(dice_rolls)

    return statroll


def get_coc_statroll() -> dict[str, int]:
    # Based on CoC 7e
    return {
        # These characteristics use the formula 5*3d6
        "STR": 5 * roll_dice(3, 6, 0),
        "CON": 5 * roll_dice(3, 6, 0),
        "DEX": 5 * roll_dice(3, 6, 0),
        "APP": 5 * roll_dice(3, 6, 0),
        "POW": 5 * roll_dice(3, 6, 0),

        # These characteristics use the formula 5*(2d6 + 6)
        "SIZ": 5 * (roll_dice(2, 6, 6)),
        "INT": 5 * (roll_dice(2, 6, 6)),
        "EDU": 5 * (roll_dice(2, 6, 6)),
        "LUC": 5 * (roll_dice(2, 6, 6)),

        # This stat uses a single d10
        "Bonus": random.randint(1, 10),
    }


def get_pf_statroll() -> dict[str, int]:
    # Based on Pathfinder 2e
    statroll = {
        "STR": 0,
        "DEX": 0,
        "CON": 0,
        "INT": 0,
        "WIS": 0,
        "CHA": 0,
    }

    # All ability scores use 4d6 drop lowest
    for stat in statroll:
        dice_rolls = [random.randint(1, 6) for _ in range(4)]
        statroll[stat] = sum(dice_rolls) - min(dice_rolls)

    return statroll


# List of game options & associated functions for stat rolls
STATROLL_GAME_OPTIONS = [
    StatrollGame(
        "Dungeons & Dragons",
        ["dnd", "d&d", "dungeons and dragons", "dungeons & dragons", "dungeons n dragons"],
        get_dnd_statroll,
    ),
    StatrollGame(
        "Call of Cthulhu",
        ["coc", "call of cthulhu"],
        get_coc_statroll,
    ),
    StatrollGame(
        "Pathfinder",
        ["pf", "pathfinder", "path finder"],
        get_pf_statroll,
    ),
]
