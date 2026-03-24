"""Command utilities.

This module contains classes and functions related to sending inputs to command functions
and handling their responses.
"""

from __future__ import annotations  # Python 3.14 feature for deferred annotations

import functools
import random
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import discord
from aiopath import AsyncPath
from discord.errors import HTTPException
from discord.ext.commands import Bot as DiscordBot
from discord.ext.commands import Context as DiscordContext
from loguru import logger
from telegram import Update as TelegramUpdate
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import Application as TelegramBot
from telegram.ext import CallbackContext as TelegramContext

import common


# ==========================
# COMMANDS & RESPONSES
# ==========================
# region
class UserCommand:
    """Class that stores information regarding messages or commands sent to the bot.

    This class acts as a wrapper for both PTB's CallbackContext and Update, and Discord.py's Context. This allows
    commands to easily be written that support both platforms.
    """

    def __init__(self, target_bot: AnyBotAnn, context: AnyContextAnn, update: TelegramUpdate | None) -> None:
        self.target_bot = target_bot
        self.context = context
        self.update = update
        self.response: CommandResponse | None = None

        if isinstance(target_bot, TelegramBot) and update is None:
            error_msg = "Update cannot be None when sending message to telegram bot"
            raise ValueError(error_msg)

        if isinstance(target_bot, TelegramBot) != isinstance(context, TelegramContext):
            error_msg = f"Bot type (telegram bot) and context type ({type(context).__name__}) must match"
            raise TypeError(error_msg)

        if isinstance(target_bot, DiscordBot) != isinstance(context, DiscordContext):
            error_msg = f"Bot type (discord bot) and context type ({type(context).__name__}) must match"
            raise TypeError(error_msg)

    def get_command_name(self) -> str | None:
        """Return name of the command that was called, or None if no command was called."""
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None:
                raise MissingUpdateInfoError(self)

            if (text := self.update.message.text) is not None and text.startswith('/'):
                return text.split()[0][1:]

            if (caption := self.update.message.caption) is not None and caption.startswith('/'):
                return caption.split()[0][1:]

        elif isinstance(self.context, DiscordContext):
            if self.context.command is not None:
                return self.context.command.name

        return None

    async def track_user_id(self) -> None:
        """Write the calling user's name and ID to a json file for later retrieval."""
        id_dict: dict[str, dict[str, str]] = await common.try_read_json(common.PATH_TRACK_USERID, {})
        username = (await self.get_user_name()).lower()
        user_id = self.get_user_id()
        platform_str = self.get_platform_string()

        if platform_str in id_dict:
            id_dict[platform_str][username] = user_id

        else:
            id_dict[platform_str] = {username: user_id}

        await common.write_json_to_file(common.PATH_TRACK_USERID, id_dict)

    async def get_user_name(self, *, map_name: bool = False) -> str:
        """Return the username of the user that sent the command or message."""
        username = None
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None or self.update.message.from_user is None:
                raise MissingUpdateInfoError(self)

            username = self.update.message.from_user.username

        elif isinstance(self.context, DiscordContext):
            username = self.context.author.name

        if username is None:
            raise InvalidBotTypeError(self)

        if map_name:
            return await self.map_username(username)

        return username

    def get_user_id(self) -> str:
        """Return the user ID of the user that sent the command or message."""
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None or self.update.message.from_user is None:
                raise MissingUpdateInfoError(self)

            return str(self.update.message.from_user.id)

        if isinstance(self.context, DiscordContext):
            return str(self.context.author.id)

        raise InvalidBotTypeError(self)

    async def get_id_by_username(self, username: str) -> str | None:
        """Attempt to retrieve the user ID belonging to the provided username.

        This ID is platform-specific (Discord, Telegram) and can only be retrieved if the
        user has interacted with this bot before and was tracked by UserCommand.track_user_id()
        """
        id_dict = await common.try_read_json(common.PATH_TRACK_USERID, {})
        platform_str = self.get_platform_string()

        if platform_str in id_dict and username in id_dict[platform_str]:
            return id_dict[platform_str][username]

        return None

    def is_private(self) -> bool:
        """Return whether the command was called in a private chat or a group chat."""
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None:
                raise MissingUpdateInfoError(self)

            return self.update.message.chat.type == "private"

        if isinstance(self.context, DiscordContext):
            return self.context.guild is None

        raise InvalidBotTypeError(self)

    def get_args_list(self) -> list[str]:
        """Return the list of arguments provided with the command.

        Example: /test a b c -> ['a', 'b', 'c']
        """
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None:
                raise MissingUpdateInfoError(self)

            if (text := self.update.message.text) is not None:
                if text.startswith('/'):
                    return text.split()[1:]
                return text.split()

            if (caption := self.update.message.caption) is not None:
                if caption.startswith('/'):
                    return caption.split()[1:]
                return caption.split()

            raise MissingUpdateInfoError(self)

        if isinstance(self.context, DiscordContext):
            if (caption := self.context.message.content).startswith('/'):
                return caption.split()[1:]
            return caption.split()

        raise InvalidBotTypeError(self)

    def get_first_arg(self, *, lowercase: bool = False) -> str | None:
        """Return the first element from the argument list, all lowercase if lowercase=True.

        Example: /test a b c -> 'a'
        """
        args_list = self.get_args_list()

        if args_list:
            if lowercase:
                return args_list[0].lower()
            return args_list[0]

        return None

    def get_user_message(self) -> str:
        """Return the message that this user sent with this UserCommand.

        Examples:
            Hello world! -> 'Hello world!'
            /test a b c -> 'a b c'
        """
        return ' '.join(self.get_args_list())

    async def get_user_attachments(self) -> list[bytearray] | BadRequest | None:
        if isinstance(self.update, TelegramUpdate):
            # NOTE: If this function is returning None for a TelegramBot when you're expecting files,
            # make sure that you have your command registered in FILE_COMMAND_LIST and not COMMAND_LIST!
            if self.update.message is None:
                raise MissingUpdateInfoError(self)

            attachments: list[bytearray] = []
            for file in [self.update.message.document, self.update.message.audio, self.update.message.voice]:
                if file is not None:
                    try:
                        telegram_file = await file.get_file()
                    except BadRequest as e:
                        return e

                    byte_data = await telegram_file.download_as_bytearray()
                    attachments.append(byte_data)

            return attachments or None

        if isinstance(self.context, DiscordContext):
            attachments = [bytearray(await att.read()) for att in self.context.message.attachments]
            return attachments or None

        raise InvalidBotTypeError(self)

    async def get_user_prompt(self) -> str | None:
        # This is used for prompting the GPT chat completion model
        sender = await self.get_user_name(map_name=True)

        if self.response is not None:
            user_message = self.response.user_message
        else:
            user_message = self.get_user_message()

        if not user_message:
            return None

        return f'{sender}: {user_message}'

    async def is_admin(self) -> bool:
        """Return whether the message sender is on the bot's admin list or superadmin list."""
        user_id = self.get_user_id()
        admin_dict: dict[str, dict[str, list[str]]] = await common.try_read_json(common.PATH_ADMIN_LIST, {})
        platform_str = self.get_platform_string()

        if platform_str not in admin_dict:
            return False

        if "admin" in admin_dict[platform_str] and user_id in admin_dict[platform_str]["admin"]:
            return True

        # Superadmin rights also give you normal admin rights
        return "superadmin" in admin_dict[platform_str] and user_id in admin_dict[platform_str]["superadmin"]

    async def is_superadmin(self) -> bool:
        """Return whether the message sender is on the bot's superadmin list.

        Normal admin rights are NOT sufficient for this to return True.
        """
        user_id = self.get_user_id()
        admin_dict: dict[str, dict[str, list[str]]] = await common.try_read_json(common.PATH_ADMIN_LIST, {})
        platform_str = self.get_platform_string()

        if platform_str not in admin_dict:
            return False

        return "superadmin" in admin_dict[platform_str] and user_id in admin_dict[platform_str]["superadmin"]

    async def assign_super_if_none(self) -> None:
        # Gives the user the superadmin role if no superadmins are assigned
        user_id = self.get_user_id()
        user_name = await self.get_user_name()
        admin_dict: dict[str, dict[str, list[str]]] = await common.try_read_json(common.PATH_ADMIN_LIST, {})
        platform_str = self.get_platform_string()

        message_str = f"Assigned vacant superadmin role for {platform_str} to {user_id} ({user_name})"
        if platform_str not in admin_dict:
            admin_dict[platform_str] = {"superadmin": [user_id]}
            logger.warning(message_str)
            await common.write_json_to_file(common.PATH_ADMIN_LIST, admin_dict)
            return

        if "superadmin" not in admin_dict[platform_str] or not admin_dict[platform_str]["superadmin"]:
            admin_dict[platform_str]["superadmin"] = [user_id]
            logger.warning(message_str)
            await common.write_json_to_file(common.PATH_ADMIN_LIST, admin_dict)
            return

    def get_chat_id(self) -> str:
        if isinstance(self.update, TelegramUpdate):
            if self.update.message is None:
                raise MissingUpdateInfoError(self)

            return str(self.update.message.chat.id)

        if isinstance(self.context, DiscordContext):
            if self.context.guild is not None:
                return str(self.context.guild.id)

            return str(self.context.channel.id)

        raise InvalidBotTypeError(self)

    async def is_whitelisted(self) -> bool:
        """Return whether the chat is on the bot's whitelist."""
        chat_id = self.get_chat_id()
        platform_str = self.get_platform_string()
        whitelist: dict[str, list[str]] = await common.try_read_json(common.PATH_WHITELIST, {})

        if platform_str not in whitelist:
            return False

        return chat_id in whitelist[platform_str]

    async def get_and_send_response(self, command_function: CommandAnn) -> None:
        config = await common.Config.load()

        # Send the command to the bot and await its response
        self.response = await command_function(self)

        text_response = None
        if self.response.send_chat and self.response.bot_message:
            text_response = self.response.bot_message

        if text_response is not None and len(text_response) > config.main.maxmessagelength.value:
            text_response = text_response[:config.main.maxmessagelength.value]
            logger.info(f"Cut off bot response at {config.main.maxmessagelength.value} characters")

        try:
            # Respond with a sound effect
            if isinstance(self.response, SoundResponse):
                await self.send_sound_response(self.response, text_response)

            # Respond with a file
            elif isinstance(self.response, FileResponse):
                await self.send_file_response(self.response, text_response)

            # Respond with text
            elif text_response:
                await self.send_text_response(text_response)

        except (BadRequest, TimedOut, NetworkError, HTTPException) as e:
            await self.send_text_response(common.TXT_BZZZT_ERROR)

            command_name = self.get_command_name()
            user_message = self.get_user_message()
            error_string = f"{type(e).__name__}: {e}"

            if command_name is not None:
                command_string = f"{command_name} {user_message}".strip()
                logger.error(f"Command '/{command_string}' encountered an exception ({error_string})")
            else:
                logger.error(f"User message '{user_message}' encountered an exception ({error_string})")

            # Re-raise BadRequests, as these indicate a bug with the script that will need to be fixed
            if isinstance(e, BadRequest):
                raise

        # Add the command and its response to memory if necessary
        if self.response.record_memory:
            user_prompt = await self.get_user_prompt()
            await common.append_to_gpt_memory(user_prompt=user_prompt, bot_response=self.response.bot_message)

    async def send_text_response(self, response: str | None) -> None:
        if isinstance(self.context, TelegramContext) and isinstance(self.update, TelegramUpdate):
            if self.update.effective_chat is None:
                raise MissingUpdateInfoError(self)

            await self.context.bot.send_message(chat_id=self.update.effective_chat.id, text=response)

        elif isinstance(self.context, DiscordContext):
            await self.context.send(response)

        else:
            raise InvalidBotTypeError(self)

    async def send_file_response(self, response: FileResponse, text: str | None) -> None:
        if isinstance(self.context, TelegramContext) and isinstance(self.update, TelegramUpdate):
            if self.update.effective_chat is None:
                raise MissingUpdateInfoError(self)

            await self.context.bot.send_document(
                chat_id=self.update.effective_chat.id,
                document=response.file_path,
                caption=text,
            )

        elif isinstance(self.context, DiscordContext):
            await self.context.send(content=text, file=discord.File(response.file_path))

        else:
            raise InvalidBotTypeError(self)

        # Delete the file that was sent if it was a temporary file
        if response.temp:
            await AsyncPath(response.file_path).unlink()

    async def send_sound_response(self, response: SoundResponse, text: str | None) -> None:
        if isinstance(self.context, TelegramContext) and isinstance(self.update, TelegramUpdate):
            if self.update.effective_chat is None:
                raise MissingUpdateInfoError(self)

            await self.context.bot.send_voice(
                chat_id=self.update.effective_chat.id,
                voice=response.file_path,
                caption=text,
            )

        elif isinstance(self.context, DiscordContext):
            await self.context.send(content=text, file=discord.File(response.file_path))

        else:
            raise InvalidBotTypeError(self)

        # Delete the file that was sent if it was a temporary file
        if response.temp:
            await AsyncPath(response.file_path).unlink()

    def is_telegram(self) -> bool:
        """Return whether this UserCommand object was sent to a Telegram bot or not."""
        return isinstance(self.target_bot, TelegramBot)

    def is_discord(self) -> bool:
        """Return whether this UserCommand object was sent to a Discord bot or not."""
        return isinstance(self.target_bot, DiscordBot)

    def get_platform_string(self) -> str:
        """Return the string for the user/bot's current platform.

        Platform string is used to store/retrieve platform-dependent data like user IDs and chat IDs.
        Current platform strings are "telegram" and "discord".
        """
        if self.is_telegram():
            return "telegram"
        if self.is_discord():
            return "discord"
        raise InvalidBotTypeError(self)

    def get_user_voice_channel(self) -> discord.VoiceChannel | None:
        """Return the voice channel that the user who sent this UserCommand is currently in."""
        if not isinstance(self.context, DiscordContext):
            return None

        author = self.context.author
        if not isinstance(author, discord.Member):
            return None

        if not isinstance(author.voice, discord.VoiceState):
            return None

        if not isinstance(author.voice.channel, discord.VoiceChannel):
            return None

        return author.voice.channel

    def get_bot_voice_client(self) -> discord.VoiceClient | None:
        """Return the bot's voice client if it is a DiscordBot and in a voice channel, otherwise None."""
        if not isinstance(self.context, DiscordContext):
            return None

        if not isinstance(self.context.voice_client, discord.VoiceClient):
            return None

        return self.context.voice_client

    async def map_username(self, username: str) -> str:
        username_map = await common.try_read_json(common.PATH_USERNAME_MAP, {})

        try:
            corrected_name = username_map[username.lower()]
        except KeyError:
            return username

        return corrected_name


@dataclass(kw_only=True)
class CommandResponse:
    """Class representing the bot's response to a UserCommand."""

    user_message: str
    bot_message: str
    record_memory: bool = field(default=True)  # Whether user_message and bot_message should be recorded to memory
    send_chat: bool = field(default=True)  # Whether bot_message should be sent to chat


@dataclass(kw_only=True)
class FileResponse(CommandResponse):
    """Subclass of CommandResponse for when the response has a file attached."""

    file_path: Path  # Path of file relative to script
    temp: bool = field(default=False)  # Whether the file should be deleted after its sent
    record_memory: bool = field(default=True)
    send_chat: bool = field(default=False)


@dataclass(kw_only=True)
class SoundResponse(FileResponse):
    """Subclass of FileResponse for when the response is to be sent as a voice message.

    Note that the Discord API does not currently (2025-05-22) support bots sending voice messages,
    so the distinction is only important for Telegram.
    """


@dataclass(kw_only=True)
class NoResponse(CommandResponse):
    """Subclass of CommandResponse for when there is no response, and thus no message is to be sent by the bot."""

    def __init__(self) -> None:
        super().__init__(user_message='', bot_message='', record_memory=False, send_chat=False)
# endregion


# ==========================
# EXCEPTION TYPES
# ==========================
# region
class InvalidBotTypeError(TypeError):
    """Exception type to be raised if a function expects a TelegramBot or DiscordBot but receives something else."""

    def __init__(self, user_command: UserCommand, message: str | None = None) -> None:
        self.message = message
        if message is None:
            bot_type = type(user_command.target_bot).__name__
            context_type = type(user_command.context).__name__
            update_type = type(user_command.update).__name__
            type_string = f"Bot: {bot_type}, Context: {context_type}, Update: {update_type}?"
            self.message = f"Function failed for provided types ({type_string})"

        super().__init__(self.message)


class MissingUpdateInfoError(ValueError):
    """Exception type to be raised if a function is passed a Telegram Update but it is missing information."""

    def __init__(self, user_command: UserCommand, message: str | None = None) -> None:
        update = user_command.update
        if message is not None:
            self.message = message

        elif update is None:
            self.message = "Update cannot be None"

        elif update.message is None:
            self.message = "Update.message cannot be None"

        elif (update.message.text is None and update.message.caption is None):
            self.message = "Update.message.text and Update.message.caption cannot both be None"

        elif update.message.from_user is None:
            self.message = "Update.message.from_user cannot be None"

        elif update.effective_chat is None:
            self.message = "Update.effective_chat cannot be None"

        if update is not None:
            logger.error(f"UPDATE DICT: {update.to_dict()}")

        super().__init__(self.message)
# endregion


# ==========================
# TYPE ANNOTATIONS
# ==========================
# region
CommandAnn = Callable[[UserCommand], Awaitable[CommandResponse]]
TelegramBotAnn = TelegramBot[Any, Any, Any, Any, Any, Any]
DiscordBotAnn = DiscordBot
AnyBotAnn = TelegramBotAnn | DiscordBotAnn
TelegramContextAnn = TelegramContext[Any, Any, Any, Any]
DiscordContextAnn = DiscordContext[Any]
AnyContextAnn = TelegramContextAnn | DiscordContextAnn
TelegramFuncAnn = Callable[[TelegramUpdate, TelegramContextAnn], Coroutine[Any, Any, None]]
DiscordFuncAnn = Callable[[DiscordContextAnn], Coroutine[Any, Any, None]]
# endregion


# ==========================
# WRAPPERS
# ==========================
# region
def requireadmin(function: CommandAnn) -> CommandAnn:
    """Wrap function with @requireadmin decorator to prevent use without admin rights."""
    @functools.wraps(function)
    async def admin_wrapper(user_command: UserCommand) -> CommandResponse:
        config = await common.Config.load()
        if config.main.requireadmin.value and not await user_command.is_admin():
            user_message = "Can I do that sensitive thing that requires superadmin rights?"
            return CommandResponse(user_message=user_message, bot_message=random.choice(common.TXT_NO_PERMISSIONS))

        return await function(user_command)

    admin_wrapper.requireadmin = True  # pyrefly:ignore
    return admin_wrapper


def requiresuper(function: CommandAnn) -> CommandAnn:
    """Wrap function with @requiresuper decorator to prevent use without superadmin rights.

    This is strictly stronger than admin rights, normal admin rights are insufficent
    """
    @functools.wraps(function)
    async def superadmin_wrapper(user_command: UserCommand) -> CommandResponse:
        config = await common.Config.load()
        if config.main.requireadmin.value and not await user_command.is_superadmin():
            user_message = "Can I do that sensitive thing that requires superadmin rights?"
            return CommandResponse(user_message=user_message, bot_message=random.choice(common.TXT_NO_PERMISSIONS))

        return await function(user_command)

    superadmin_wrapper.requiresuper = True  # pyrefly:ignore
    return superadmin_wrapper


def wrap_telegram_command(bot: TelegramBotAnn, command_function: CommandAnn) -> TelegramFuncAnn:
    @functools.wraps(command_function)
    async def telegram_wrapper(update: TelegramUpdate, context: TelegramContextAnn) -> None:
        if update.message is None:
            return

        config = await common.Config.load()
        user_command = UserCommand(bot, context, update)

        # Track this user's platform, name, and user ID. This powers the /getuserid command
        await user_command.track_user_id()

        # If the whitelist is enforced, don't allow interacting with this bot unless on the list
        if config.main.whitelisttelegram.value and not await user_command.is_whitelisted():
            logger.warning(f"Whitelist rejected chat ID {user_command.get_chat_id()} for Telegram Bot")
            return

        # If there are no superadmins assigned to this bot, assign this user as the superadmin
        if config.main.autosupertelegram.value:
            await user_command.assign_super_if_none()

            # Automatically disable this setting after checking for superadmins to prevent accidents
            config.main.autosupertelegram.value = False
            await config.save_config()

        await user_command.get_and_send_response(command_function)

    return telegram_wrapper


def wrap_discord_command(bot: DiscordBotAnn, command_function: CommandAnn) -> DiscordFuncAnn:
    @functools.wraps(command_function)
    async def discord_wrapper(context: DiscordContextAnn) -> None:
        config = await common.Config.load()
        user_command = UserCommand(bot, context, None)

        # Track this user's platform, name, and user ID. This powers the /getuserid command
        await user_command.track_user_id()

        # If the whitelist is enforced, don't allow interacting with this bot unless on the list
        if config.main.whitelistdiscord.value and not await user_command.is_whitelisted():
            logger.warning(f"Whitelist rejected chat ID {user_command.get_chat_id()} for Discord Bot")
            return

        # If there are no superadmins assigned to this bot, assign this user as the superadmin
        if config.main.autosuperdiscord.value:
            await user_command.assign_super_if_none()

            # Automatically disable this setting after checking for superadmins to prevent accidents
            config.main.autosuperdiscord.value = False
            await config.save_config()

        await user_command.get_and_send_response(command_function)

    return discord_wrapper
# endregion
