import asyncio
from telethon.sync import TelegramClient
from telethon import functions, Button
import telethon.password as pwd_mod

from src.bot import bot_client
from src.common.database_utils import get_users, get_feeds, update_feed, save_feeds
from src.common.utils import list_to_str_newline, get_display_name
from src.common.database_utils import Channel

from src import config

import logging
logger = logging.getLogger(__name__)


async def get_users_channel_links(event):
    sender_id = event.chat_id
    users_channels_links = []
    users = get_users()
    users_channel_id_list = users[sender_id]
    if len(users_channel_id_list) == 0:
        await event.reply("You haven't added the bot to any of your channels yet")
    else:
        for ch_id in users_channel_id_list:
            ch = Channel(channel_id=ch_id, client=bot_client)
            if ch.link is None:
                users_channels_links.append(ch.name)
            else:
                users_channels_links.append(ch.link)

    return users_channels_links


async def add_to_channel(src_ch: Channel, dst_ch: Channel, sender_id):  # TODO: add types
    # TODO: add any number of channels before the last/destination one

    users = get_users()
    if dst_ch.id not in users[sender_id]:
        await bot_client.send_message(sender_id,
                                      "You are not allowed to perform this action. Try to add the bot to your channel as admin.")
        return
    feeds = get_feeds()

    if len(feeds[dst_ch.id]) > 20:
        logger.info(f"Channel {dst_ch} faced a limit of source channels")
        await bot_client.send_message(sender_id, "You are not allowed to have more than 20 source channel")
        return

    existing_dst_channel_ids = list(feeds.keys())
    if src_ch.id in existing_dst_channel_ids or (src_ch.id == dst_ch.id):  # will not be in feeds if this is a first subscription
        # TODO: think about potential solution
        await bot_client.send_message(sender_id,
                                      "You can not add somebody's (including your) target channel as your source because of potential infinite loops")
        logger.warning(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) tried to add {src_ch} to {dst_ch}",
                       exc_info=True)
        return

    if src_ch.id in feeds[dst_ch.id]:
        logger.debug(f"Channel {src_ch} is already in subs list of {dst_ch} channel")
        reading_list_links = []
        for ch_id in feeds[dst_ch.id]:
            ch = Channel(channel_id=ch_id)
            reading_list_links.append(ch.link)
        await bot_client.send_message(sender_id,
                                      f"Channel {src_ch.link} is already in your reading list:\n{list_to_str_newline(reading_list_links)}")
        return

    update_feed(feeds, dst_ch, src_ch, add_not_remove=True)
    save_feeds(feeds)

    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) added {src_ch} to {dst_ch}",
                 exc_info=True)

    reading_list_links = []
    for ch_id in feeds[dst_ch.id]:
        ch = Channel(channel_id=ch_id)
        reading_list_links.append(ch.link)
    await bot_client.send_message(sender_id, f"Added! Now your reading list is the following:\n{list_to_str_newline(reading_list_links)}")


async def get_answer_in_conv(event, question: str, timeout=300) -> str:
    # TODO: check if event.chat_id == event.sender_id
    sender_id = event.chat_id
    async with bot_client.conversation(event.sender_id, timeout=timeout) as conv:
        try:
            await conv.send_message(question, buttons=Button.force_reply())
            reply = await conv.get_reply()
            if not reply.text:
                await event.reply("You can only send a text message!")
                return

            await conv.send_message('Your input is received', buttons=Button.clear())  # TODO: remove the messave with force reply
            # TODO: menu disappears here. return it back
        except asyncio.exceptions.TimeoutError:
            await event.reply("Timeout for the input. Please, perform the procedure once again",
                              buttons=Button.clear())  # both do not actually clear the force reply
            # TODO: try removing the message with force_reply
            # await event.reply("Test Button.text",
            #                   buttons=Button.text('button text'))  # both do not actually clear the force reply
            logger.error(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) faced a timeout in get_answer_in_conv")  # TODO: catch outside to name properly
            # return
            raise

        return reply.text


# for some reason CreateChannelRequest doesn't want to work in sync
async def create_channel(client: TelegramClient,
                         channel_title: str = 'My awesome title',
                         about: str = '',
                         supergroup=False):
    result = await client(functions.channels.CreateChannelRequest(
        title=channel_title,
        about=about,
        megagroup=supergroup,
    ))
    # print(result.stringify())
    return result


async def transfer_channel_ownership(client, channel_id, to_user_id):
    pwd = await client(functions.account.GetPasswordRequest())
    my_srp_password = pwd_mod.compute_check(pwd, config.pass_2fa)
    logger.debug('Checked password before performing EditCreatorRequest')
    await client(functions.channels.EditCreatorRequest(
        channel=channel_id,
        user_id=to_user_id,
        password=my_srp_password
        # password=pwd
    ))
    # except Exception as e:
    #     await event.edit(str(e))
    # else:
    #     await event.edit("Transferred 🌚")
