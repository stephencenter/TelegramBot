"""Module for testing UserCommands and its methods.

This module simulates Telegram and Discord bots and their contexts to unit
test the various methods belonging to the UserCommand class.
"""

from __future__ import annotations

import asyncio
import string
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from discord.ext.commands import Bot as DiscordBotType
from discord.ext.commands import Context as DiscordContextType
from loguru import logger
from telegram import Update as TelegramUpdateType
from telegram.ext import Application as TelegramBotType
from telegram.ext import CallbackContext as TelegramContextType

from command import UserCommand


# ==========================
# TELEGRAM CLASSES
# ==========================
# region
class FakeTelegramApplication:
    """Dummy Telegram Application class for unit testing."""

    @property
    def __class__(self) -> type:
        return TelegramBotType


@dataclass
class FakeTelegramUpdate:
    """Dummy Telegram Update class for unit testing."""

    message: FakeTelegramMessage | None

    @property
    def __class__(self) -> type:
        return TelegramUpdateType


class FakeTelegramContext:
    """Dummy Telegram Context class for unit testing."""

    @property
    def __class__(self) -> type:
        return TelegramContextType


@dataclass
class FakeTelegramUser:
    """Dummy Telegram User class for unit testing."""

    username: str
    id: str


@dataclass
class FakeTelegramMessage:
    """Dummy Telegram Message class for unit testing."""

    text: str | None
    caption: str | None
    chat: FakeTelegramChat
    from_user: FakeTelegramUser


@dataclass
class FakeTelegramChat:
    """Dummy Telegram Chat class for unit testing."""

    id: str
    type: str
# endregion


# ==========================
# DISCORD CLASSES
# ==========================
# region
class FakeDiscordBot:
    """Dummy Discord Bot class for unit testing."""

    @property
    def __class__(self) -> type:
        return DiscordBotType


@dataclass
class FakeDiscordContext:
    """Dummy Discord Context class for unit testing."""

    message: FakeDiscordMessage
    author: FakeDiscordUser
    guild: FakeDiscordGuild | None
    channel: FakeDiscordChannel | None

    @property
    def __class__(self) -> type:
        return DiscordContextType


@dataclass
class FakeDiscordUser:
    """Dummy Discord User class for unit testing."""

    name: str
    id: str


@dataclass
class FakeDiscordMessage:
    """Dummy Discord Message class for unit testing."""

    content: str
    author: FakeDiscordUser


@dataclass
class FakeDiscordGuild:
    """Dummy Discord Guild class for unit testing."""

    id: str


@dataclass
class FakeDiscordChannel:
    """Dummy Discord Channel class for unit testing."""

    id: str
# endregion


def telegram_create_usercommands(test_input: TestInput) -> tuple[UserCommand, UserCommand]:
    bot = FakeTelegramApplication()
    context = FakeTelegramContext()
    chat = FakeTelegramChat(test_input.chat_id, "private" if test_input.is_private else "public")
    user = FakeTelegramUser(test_input.user_name, test_input.user_id)
    message_a = FakeTelegramMessage(test_input.text_input, None, chat, user)
    message_b = FakeTelegramMessage(None, test_input.text_input, chat, user)
    update_a = FakeTelegramUpdate(message_a)
    update_b = FakeTelegramUpdate(message_b)

    return UserCommand(bot, context, update_a), UserCommand(bot, context, update_b)  # type: ignore


def discord_create_usercommand(test_input: TestInput) -> UserCommand:
    bot = FakeDiscordBot()
    author = FakeDiscordUser(test_input.user_name, test_input.user_id)
    if test_input.is_private:
        guild = None
        channel = FakeDiscordChannel(test_input.chat_id)
    else:
        guild = FakeDiscordGuild(test_input.chat_id)
        channel = None

    message = FakeDiscordMessage(test_input.text_input, author)
    context = FakeDiscordContext(message, author, guild, channel)

    return UserCommand(bot, context, None)  # type: ignore


# ==========================
# TESTS
# ==========================
# region
async def test_args_list(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.get_args_list() == item.args_list


async def test_first_arg(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.get_first_arg() == item.first_arg


async def test_user_message(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.get_user_message() == item.user_msg


async def test_user_name(user_command: UserCommand, item: TestInput) -> bool:
    return await user_command.get_user_name() == item.user_name


async def test_user_id(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.get_user_id() == item.user_id


async def test_chat_id(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.get_chat_id() == item.chat_id


async def test_chat_type(user_command: UserCommand, item: TestInput) -> bool:
    return user_command.is_private() == item.is_private


async def test_user_prompt(user_command: UserCommand, item: TestInput) -> bool:
    return await user_command.get_user_prompt() == item.user_prompt


TEST_LIST = [
    test_args_list,
    test_first_arg,
    test_user_message,
    test_user_name,
    test_user_id,
    test_chat_id,
    test_chat_type,
    test_user_prompt,
]
# endregion


# ==========================
# INPUTS
# ==========================
# region
@dataclass(kw_only=True)
class TestInput:
    """Dataclass for describing the input for a unit test case."""

    text_input: str
    user_name: str
    user_id: str
    chat_id: str
    args_list: list[str]
    first_arg: str | None
    user_msg: str
    user_prompt: str | None
    is_private: bool


INPUT_LIST: list[TestInput] = [
    TestInput(
        text_input="test 123 abc 456",
        user_name="test_user",
        user_id="11234",
        chat_id="321",
        args_list=["test", "123", "abc", "456"],
        first_arg="test",
        user_msg="test 123 abc 456",
        user_prompt="test_user: test 123 abc 456",
        is_private=True,
    ),
    TestInput(
        text_input="/test test 123 abc 456",
        user_name="test_user",
        user_id="11234",
        chat_id="321",
        args_list=["test", "123", "abc", "456"],
        first_arg="test",
        user_msg="test 123 abc 456",
        user_prompt="test_user: test 123 abc 456",
        is_private=False,
    ),
    TestInput(
        text_input="/test",
        user_name="test_user",
        user_id="11234",
        chat_id="321",
        args_list=[],
        first_arg=None,
        user_msg="",
        user_prompt=None, is_private=True,
    ),
    TestInput(
        text_input="/",
        user_name="test_user",
        user_id="11234",
        chat_id="321",
        args_list=[],
        first_arg=None,
        user_msg="",
        user_prompt=None, is_private=False,
    ),
    TestInput(
        text_input="",
        user_name="test_user",
        user_id="11234",
        chat_id="321",
        args_list=[],
        first_arg=None,
        user_msg="",
        user_prompt=None, is_private=True,
    ),
]
# endregion


class TestResult:
    """Class for describing the result/output for a unit test case."""

    def __init__(self, *, passed: bool, test_name: str, index: int, subindex: str) -> None:
        self.passed = passed
        self.test_name = test_name
        self.index = index
        self.subindex = subindex
        self.result_string = f"Item {index}{subindex} {'passed' if passed else 'failed'} {test_name}()"


async def perform_tests() -> AsyncGenerator[TestResult]:
    for test in TEST_LIST:
        for index, item in enumerate(INPUT_LIST):
            # We create two telegram UserCommands, one where the user message is in message.text and
            # another where the user message is in message.caption, as both are possible and need to be tested.
            # We only need to create one discord UserCommand because it doesn't have this quirk
            command_list = [*telegram_create_usercommands(item), discord_create_usercommand(item)]

            # This zip pairs each UserCommand in command_list with a letter of the alphabet
            for command, letter in zip(command_list, string.ascii_lowercase, strict=False):
                result = await test(command, item)
                yield TestResult(passed=result, test_name=test.__name__, index=index, subindex=letter)


async def main() -> None:
    async for test_result in perform_tests():
        if test_result.passed:
            logger.info(test_result.result_string)
        else:
            logger.error(test_result.result_string)

    logger.info("Tests complete.")


if __name__ == "__main__":
    asyncio.run(main())
    input("Press enter/return to exit ")
