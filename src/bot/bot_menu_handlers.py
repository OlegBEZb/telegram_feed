import asyncio
from math import ceil

from telethon import events, types, Button
from telethon.events import StopPropagation

from src.bot import bot_client, NO_ARG_CLI_COMMANDS, CLI_COMMANDS
from src.common.database_utils import get_users, get_feeds
from src.common.channel import Channel, get_display_name
from src.bot.bot_utils import add_to_channel, get_answer_in_conv

from src.common.utils import chunks
from src.common.decorators import check_direct

from src import config

import logging
logger = logging.getLogger(__name__)


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


def paginate_menu(page_number: int, cmd_list: list, shape=(3, 2)):
    number_of_rows, number_of_cols = shape

    modules = [Button.text(text=cmd) for cmd in cmd_list]

    button_rows = list(chunks(modules, number_of_cols))

    max_num_pages = ceil(len(button_rows) / number_of_rows)
    modulo_page = page_number % max_num_pages
    if len(button_rows) > number_of_rows:
        button_rows = button_rows[modulo_page * number_of_rows: number_of_rows * (modulo_page + 1)] + [
            (Button.text("⏮ prev page️"),
             Button.text("⏹️ reopen again"),
             Button.text("⏭️ next page")
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


@bot_client.on(events.NewMessage(pattern='/menu'))
@check_direct
async def command_menu(event):
    sender_id = event.chat_id

    cmd_list = [btn_name for _, (btn_name, _) in CLI_COMMANDS.items()]
    menu_buttons = paginate_menu(page_number=0, cmd_list=cmd_list, shape=(3, 2))
    await bot_client.send_message(sender_id, "Use the menu below", buttons=menu_buttons)
    logger.debug(f"Sent menu to {await get_display_name(bot_client, int(sender_id))} ({sender_id})")
    # do not stop as some commands call menu
    # raise StopPropagation


@bot_client.on(events.NewMessage(pattern='/help$'))  # to escape help_text
@check_direct
async def command_help(event):
    sender_id = event.chat_id

    # some commands may be called right from here. for others another sub call to get arguments is needed
    # may be addressed by level of depth
    cmd_text2data = {btn_name: (cmd if (cmd in NO_ARG_CLI_COMMANDS) else ('button_' + cmd)) for cmd, (btn_name, _) in
                     CLI_COMMANDS.items()}

    buttons = paginate_help(event, 0, cmd_text2data, "helpme")
    await event.reply("Select one of the following", buttons=buttons)
    # await bot_client.send_message(sender_id, "Select one of the following", buttons=buttons)
    logger.debug(f"Sent help to {await get_display_name(bot_client, int(sender_id))} ({sender_id})")


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/channel_info'][0]))
@bot_client.on(events.CallbackQuery(data=b"button_/channel_info"))
@check_direct
async def button_channel_info(event):
    sender_id = event.chat_id

    # users_channels_links = await get_users_channel_links(event)
    # if not users_channels_links:
    #     return
    # cmd_text2data = {str(ch_link): f"/channel_info {ch_link}" for ch_link in users_channels_links}
    users = get_users()
    users_channel_id_list = users[sender_id]
    cmd_text2data = dict()
    if len(users_channel_id_list) == 0:
        await event.reply("You haven't added the bot to any of your channels yet")
    else:
        for ch_id in users_channel_id_list:
            ch = Channel(channel_id=ch_id, client=bot_client)
            if ch.link is None:
                cmd_text2data[f"{ch.name} (id={ch.id})"] = f"/channel_info {ch.id}"  # may have the same name
            else:
                cmd_text2data[ch.link] = f"/channel_info {ch.link}"

    buttons = paginate_help(event, 0, cmd_text2data, "channel",
                            shape=(len(cmd_text2data), 1)
                            )

    await bot_client.send_message(sender_id, "Which channel info are you interested id?", buttons=buttons)
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) pressed button_/channel_info")
    raise StopPropagation


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/add_to_channel'][0]))
@bot_client.on(events.CallbackQuery(data=b"button_/add_to_channel"))
@check_direct
async def button_add_to_channel(event):
    sender_id = event.chat_id

    users = get_users()
    users_channel_id_list = users[sender_id]
    cmd_text2data = dict()
    if len(users_channel_id_list) == 0:
        await event.reply("You haven't added the bot to any of your channels yet")
    else:
        for ch_id in users_channel_id_list:
            ch = Channel(channel_id=ch_id, client=bot_client)
            if ch.link is None:
                cmd_text2data[f"{ch.name} (id={ch.id})"] = f"button_button_/add_to_channel {ch.id}"  # may have the same name
            else:
                cmd_text2data[ch.link] = f"button_button_/add_to_channel {ch.link}"

    buttons = paginate_help(event, 0, cmd_text2data, "channel",
                            shape=(len(cmd_text2data), 1)
                            )
    await bot_client.send_message(sender_id, "To which of your channels do you want to add a new source?", buttons=buttons)
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) pressed button_/add_to_channel")
    raise StopPropagation


@bot_client.on(events.CallbackQuery(pattern=b"button_button_/add_to_channel"))
@check_direct
async def button_button_add_to_channel(event):
    sender_id = event.chat_id

    if isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc
    _, dst_ch_parsable = message.split()
    dst_ch = Channel(parsable=dst_ch_parsable, client=bot_client)
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) pressed button_button_/add_to_channel with {dst_ch.name} destination channel")

    # this duplicates the code in add_to_channel but this helps to save time in case the user pressed the button so
    # there is no reason even for entering the value
    feeds = get_feeds()
    if len(feeds[dst_ch.id]) > 20 and (sender_id not in [config.my_id, 194124545]):
        logger.info(f"Channel {dst_ch} faced a limit of source channels")
        await bot_client.send_message(sender_id, "You are not allowed to have more than 20 source channels")
        await command_menu(event)
        return

    try:
        src_ch_link = await get_answer_in_conv(event, "Enter the link of the source channel to add", timeout=300)
    except asyncio.exceptions.TimeoutError:
        await command_menu(event)
        return

    try:
        # TODO: problem. due to this, usual client doesn't have this channel in cache
        # TODO: check: will it work with user_client_for_bot_cli_path = os.path.join(get_project_root(), 'src/telefeed_client')
        src_ch = Channel(channel_link=src_ch_link, client=bot_client)
    except:
        await event.reply("Was not able to process the argument. Start from pressing the button once again")
        logger.error(f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in /add_to_channel", exc_info=True)
        await command_menu(event)
        return

    await add_to_channel(src_ch=src_ch, dst_ch=dst_ch, sender_id=sender_id)
    await command_menu(event)
