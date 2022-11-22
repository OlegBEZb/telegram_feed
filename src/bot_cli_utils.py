from telethon import utils as tutils

from src import bot_client
from src.database_utils import get_users, get_feeds, update_feed, save_feeds
from src.utils import check_channel_correctness, list_to_str_newline, get_display_name

import logging
logger = logging.getLogger(__name__)


async def add_to_channel(text: str, sender_id):  # TODO: add types
    # TODO: add any number of channels before the last/destination one
    _, src_ch, dst_ch = text.split()
    # TODO: add assert for the incorrect format
    src_ch, dst_ch = check_channel_correctness(src_ch), check_channel_correctness(dst_ch)
    entity = await bot_client.get_input_entity(dst_ch)
    dst_ch_id = tutils.get_peer_id(entity)
    # dst_ch_id = get_channel_id(bot, dst_ch)
    users = get_users()
    if dst_ch_id not in users[str(sender_id)]:
        await bot_client.send_message(sender_id,
                                      "You are not allowed to perform this action. Try to add the bot to your channel as admin.")
        return
    feeds = get_feeds()
    if src_ch in feeds:
        # TODO: think about potential solution
        await bot_client.send_message(sender_id,
                                      "You can not add somebody's (including your) target channel as your source because of potential infinite loops")
        return
    update_feed(feeds, dst_ch, src_ch, add_not_remove=True)
    save_feeds(feeds)
    # TODO: add notification that the channel was already there
    await bot_client.send_message(sender_id, f"Added! Now your reading list is the following:\n{list_to_str_newline(feeds[dst_ch])}")
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) added {src_ch} to {dst_ch}", exc_info=True)
