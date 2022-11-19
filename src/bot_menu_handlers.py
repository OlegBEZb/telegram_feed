import asyncio

from telethon import events, types, Button

from math import ceil
from src import config, bot_client, NO_ARG_CLI_COMMANDS, CLI_COMMANDS
from src.database_utils import get_users
from src.bot_cli_utils import add_to_channel

from utils import get_channel_link, check_channel_correctness, get_user_display_name

import logging
logger = logging.getLogger(__name__)


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def paginate_help(event, page_number: int, button_text2data: dict, prefix: str, shape=(3, 2)):
    number_of_rows, number_of_cols = shape

    # to_check = get_page(id=event.sender_id)
    #
    # if not to_check:
    #     pagenumber.insert_one({"id": event.sender_id, "page": page_number})
    #
    # else:
    #     pagenumber.update_one(
    #         {
    #             "_id": to_check["_id"],
    #             "id": to_check["id"],
    #             "page": to_check["page"],
    #         },
    #         {"$set": {"page": page_number}},
    #     )

    modules = [Button.inline(text=k, data=v) for k, v in button_text2data.items()]

    # pairs = list(zip(modules[::number_of_cols], modules[1::number_of_cols]))
    button_rows = list(chunks(modules, number_of_cols))

    max_num_pages = ceil(len(button_rows) / number_of_rows)
    modulo_page = page_number % max_num_pages
    if len(button_rows) > number_of_rows:
        button_rows = button_rows[
                      modulo_page * number_of_rows: number_of_rows * (modulo_page + 1)
                      ] + [
                          (
                              Button.inline("⏮️", data=f"{prefix}_next({modulo_page})"),
                              Button.inline("⏹️", data="reopen_again"),
                              Button.inline("⏭️", data=f"{prefix}_next({modulo_page})"),
                          )
                      ]
    return button_rows


# @bot_client.on(events.callbackquery.CallbackQuery(data=re.compile(rb"helpme_next\((.+?)\)")))
# async def on_plug_in_callback_query_handler(event):
#     current_page_number = int(event.data_match.group(1).decode("UTF-8"))
#     buttons = paginate_help(event, current_page_number + 1, CMD_LIST, "helpme")
#     await event.edit(buttons=buttons)
#
#
# @bot_client.on(events.callbackquery.CallbackQuery(data=re.compile(rb"helpme_prev\((.+?)\)")))
# async def on_plug_in_callback_query_handler(event):
#     current_page_number = int(event.data_match.group(1).decode("UTF-8"))
#     buttons = paginate_help(event, current_page_number - 1, CMD_LIST, "helpme")
#     await event.edit(buttons=buttons)


@bot_client.on(events.NewMessage(pattern='/help$'))  # to escape help_text
async def command_help(event):
    sender_id = event.chat_id
    if not event.is_private:  # replace with event.is_group\channel\private
        await event.reply(
            "Contact me in PM to get the help menu",
            buttons=[[Button.url("Click me for help!", config.bot_url)]],
        )
        return

    # some commands may be called right from here. for others another sub call to get arguments is needed
    # may be addressed by level of depth
    cmd_text2data = {btn_name: (cmd if (cmd in NO_ARG_CLI_COMMANDS) else ('button_' + cmd)) for cmd, (btn_name, _) in
                     CLI_COMMANDS.items()}

    buttons = paginate_help(event, 0, cmd_text2data, "helpme")
    await event.reply("Select one of the following", buttons=buttons)
    # await bot_client.send_message(sender_id, "Select one of the following", buttons=buttons)
    logger.debug(f"Sent help to {await get_user_display_name(bot_client, int(sender_id))} ({sender_id})")


@bot_client.on(events.CallbackQuery(data=b"button_/channel_info"))
async def button_channel_info(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    users = get_users()
    user_channels = users[str(sender_id)]
    if not user_channels:
        await event.reply("You haven't added the bot to any of your channels yet")
        return
    user_channels_links = [await get_channel_link(bot_client, ch) for ch in user_channels]
    cmd_text2data = {str(ch): f"/channel_info {ch}" for ch in user_channels_links}
    buttons = paginate_help(event, 0, cmd_text2data, "channel",
                            shape=(len(user_channels), 1)
                            )
    await bot_client.send_message(sender_id, "Which channel info are you interested id?", buttons=buttons)


@bot_client.on(events.CallbackQuery(data=b"button_/add_to_channel"))
async def button_add_to_channel(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    users = get_users()
    user_channels = users[str(sender_id)]
    if not user_channels:
        await event.reply("You haven't added the bot to any of your channels yet")
        return
    user_channels_links = [await get_channel_link(bot_client, ch) for ch in user_channels]
    cmd_text2data = {str(ch): f"button_button_/add_to_channel {ch}" for ch in user_channels_links}
    buttons = paginate_help(event, 0, cmd_text2data, "channel",
                            shape=(len(user_channels), 1)
                            )
    await bot_client.send_message(sender_id, "To which of your channels do you want to add a new source?", buttons=buttons)


@bot_client.on(events.CallbackQuery(pattern=b"button_button_/add_to_channel"))
async def button_button_add_to_channel(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    if isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc
    _, dst_ch = message.split()

    async with bot_client.conversation(event.sender_id, timeout=60) as conv:
        try:
            await conv.send_message(
                "Enter the link of the source channel to add",
                buttons=Button.force_reply(),
            )
            msg = await conv.get_reply()
            if not msg.text:
                await event.reply("You can only set a text message!")
                return
        except asyncio.exceptions.TimeoutError:
            await event.reply("Timeout for adding a source channel. Press the button once again")
            logger.error(f"User ({sender_id}) faced a timeout in adding a source channel to add")
            return

    src_ch = msg.text
    try:
        src_ch = check_channel_correctness(src_ch)
    except:
        await event.reply(f"Was not able to process the argument. Start from pressing the button once again")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) failed in /add_to_channel", exc_info=True)
        return

    # /add_to_channel src_ch dst_ch
    await add_to_channel(text=f"/add_to_channel {src_ch} {dst_ch}",
                         sender_id=sender_id)
