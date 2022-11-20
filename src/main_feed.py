import asyncio

import argparse

from random import randint

import time

import logging

from typing import List

from telethon.sync import TelegramClient
from telethon.tl.types import TypeInputPeer
from telethon.tl.patched import Message
from telethon.tl.functions.messages import GetPeerDialogsRequest, MarkDialogUnreadRequest
from telethon.tl.functions.messages import ForwardMessagesRequest

from src.utils import get_history, start_client
from src.database_utils import get_last_channel_ids, update_last_channel_ids, get_feeds, log_messages

from src import config
from src.filtering.filter import Filter


MAIN_LOOP_DELAY_SEC_DEBUG = 10
MAIN_LOOP_DELAY_SEC_INFO = 600


# from src.bot.channel_controller_bot import get_feeds, get_users, save_users, save_feeds
bot = TelegramClient('bot_main', config.api_id, config.api_hash).start(bot_token=config.bot_token)


def forward_msgs(client: TelegramClient,
                 peer: TypeInputPeer,
                 msg_list: List[Message],
                 peer_to_forward_to: TypeInputPeer):
    """
    Forward messages in small pieces.

    :param client:
    :param personal_client:
    :param peer:
    :param msg_list:
    :param peer_to_forward_to:
    :return:
    """
    grouped_msg_ids = []  # https://github.com/LonamiWebs/Telethon/issues/1216
    msg_non_grouped = []
    last_grouped_id = -1

    for msg in reversed(msg_list):  # starting from the chronologically first
        if msg.grouped_id is not None:  # the current message is a part of a group
            if msg.grouped_id == last_grouped_id:  # extending the same group
                grouped_msg_ids.append(msg.id)
                logger.debug(f"Group {msg.grouped_id} has one more message to be sent. Total size: {len(grouped_msg_ids)}")
            else:
                if msg_non_grouped:  # a group came after a single message
                    logger.debug(f'Sending {len(msg_non_grouped)} non-grouped message(s)')
                    send_msg(client, peer, msg_non_grouped, peer_to_forward_to)
                    msg_non_grouped = []
                if grouped_msg_ids:  # in case of consequent groups
                    logger.debug(
                        f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
                    send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)
                    grouped_msg_ids = []
                last_grouped_id = msg.grouped_id
                grouped_msg_ids.append(msg.id)
                logger.debug(
                    f"Group {msg.grouped_id} has one more message to be sent. Total size: {len(grouped_msg_ids)}")
        else:  # the current message is a single message
            if grouped_msg_ids:
                logger.debug(f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
                send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)
                grouped_msg_ids = []
            msg_non_grouped.append(msg.id)
            logger.debug(f"Non-grouped messages list is extended. Total size: {len(msg_non_grouped)}")

    if msg_non_grouped:
        logger.debug(f'Sending {len(msg_non_grouped)} non-grouped message(s)')
        send_msg(client, peer, msg_non_grouped, peer_to_forward_to)

    if grouped_msg_ids:
        logger.debug(f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
        send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)


def send_msg(client: TelegramClient, peer, msg_ids_to_forward: List[int],
             peer_to_forward_to: TypeInputPeer):
    """

    :param client:
    :param peer: Anything entity-like will work if the library can find its Input version
    (e.g., usernames, Peer, User or Channel objects, etc.).
    :param msg_ids_to_forward: A list must be supplied.
    :param peer_to_forward_to: Anything entity-like will work if the library can find its Input version
    (e.g., usernames, Peer, User or Channel objects, etc.).
    :return:
    """
    if log_level != 'DEBUG':
        time.sleep(randint(5, 20))  # not to send all the messages in bulk

    logger.log(5, f'sending msg to {peer_to_forward_to}')

    try:
        client(ForwardMessagesRequest(
            from_peer=peer,  # who sent these messages?
            id=msg_ids_to_forward,  # which are the messages? = grouped_ids
            to_peer=peer_to_forward_to,  # who are we forwarding them to?
            with_my_score=True
        ))
        logger.debug(f'sent msg ids: {msg_ids_to_forward} to {peer_to_forward_to}')

        # if we sent at least one message and the recipient is our channel,
        # we can mark this as unread (by default, read (!unread))
        # can be performed only with user client, not bot
        # if peer_to_forward_to == config.MyChannel:
        #     client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        #     logger.debug(f"{peer_to_forward_to} is marked as unread")
    except:
        logger.error(f'Was not able send the message to {peer_to_forward_to}', exc_info=True)


def get_last_msg_id(client: TelegramClient, channel_id):
    messages = get_history(client=client, peer=channel_id, limit=1)
    return messages.messages[0].id


# TODO: simplify function
def main(client: TelegramClient):
    last_channel_ids = get_last_channel_ids()
    feeds = get_feeds()  # which dst channel reads what source channels
    scr2dst = {}
    for k, v in feeds.items():
        for x in v:
            scr2dst.setdefault(x, []).append(k)

    for channel_id, dst_channels in scr2dst.items():  # pool of all channels for all users
        # TODO: resurrect it back. When the channel is just added with 0 from default dict, give some small portion of
        # content. Not 100
        # if channels[channel_id] == 0:  # last message_id is 0 because the channel is added manually
        #     logger.debug(f"Channel {channel_id} is just added and doesn't have the last message id")
        #     # if channel_id.find("t.me/joinchat") != -1:
        #     #     ch = channel_id.split("/")
        #     #     req = ch[len(ch)-1]
        #     #     isCorrect = CheckCorrectlyPrivateLink(client, req)
        #     #     if not isCorrect:
        #     #         channels.pop(channel_id)
        #     #         print("Removing incorrect channel")
        #     #         break
        #     #     Subs2PrivateChat(client, req)
        #     channel_checked = check_channel_correctness(channel_id)
        #     if channel_checked == 'error':
        #         req = channel_id.split("/")[-1]
        #         if not CheckCorrectlyPrivateLink(client, req):
        #             channels.pop(channel_id)
        #             print(f"Removing incorrect channel: {channel_id}")
        #             break
        #         Subs2PrivateChat(client, req)
        #
        #     channels = OpenUpdateTime()
        try:
            # logger.log(5, f"Searching for new messages in channel: {channel_id} with the last msg_id {channels[channel_id]}")
            logger.log(5, f"Searching for new messages in channel: {channel_id}")

            do_process_channel = False

            # solution based on the last index mentioned in the json. We can't just check if there are some unread
            # messages because for that you have to be subscribed to the channel. Otherwise, you must anchor yourself to
            # some message ID in the past - this is what we do. For the just added channel with the default last
            # message id of 0, the batch will be large. But after disconnections this limit of 100 may be insufficient
            # and there will be gaps
            messages = get_history(client=client, min_id=last_channel_ids[channel_id], peer=channel_id,
                                   limit=30)
            if len(messages.messages) > 0:
                do_process_channel = True
            else:
                # solution based on telegram dialog fields
                dialog = client(GetPeerDialogsRequest(peers=[channel_id])).dialogs[0]
                # there are naturally unread messages or the channel is marked as unread
                # it's important that for channels on which you are not subscribed, both unread_count and unread_mask
                # don't work
                if dialog.unread_count or dialog.unread_mark:
                    do_process_channel = True
                    if dialog.unread_mark:
                        logger.info(f"Channel {channel_id} is marked as unread manually")
                        # if fetched message.grouped_id is not None, fetch until group changes and then send
                        messages = get_history(client=client, min_id=dialog.top_message - 1, peer=channel_id, limit=1)
                    else:  # this should not be triggered and has to be removed
                        logger.info(f"Channel {channel_id} has {dialog.unread_count} unread posts")
                        messages = get_history(client=client, min_id=dialog.read_inbox_max_id, peer=channel_id,
                                               limit=dialog.unread_count)

            if do_process_channel:
                msg_list = messages.messages  # by default their order is descending (recent to old)
                logger.debug(f"Found {len(msg_list)} message(s) in {messages.chats[0].title} (id={channel_id})")

                for dst_ch in dst_channels:
                    # TODO: perform history check later wrt the dst channel and it's rb list
                    filter_component = Filter(rule_base_check=True, history_check=True, client=client,
                                              dst_channel=dst_ch, use_common_rules=True)
                    messages_checked_list, filtering_details = filter_component.filter_messages(msg_list)
                    logger.debug(f'Before filtering: {len(msg_list)}. After {len(messages_checked_list)}')

                    asyncio.get_event_loop().run_until_complete(log_messages(client=client,
                                                                             msg_list_before=msg_list,
                                                                             filtering_details=filtering_details,
                                                                             user_channel_name=dst_ch))

                    forward_msgs(client=bot, peer=channel_id, msg_list=messages_checked_list,
                                 peer_to_forward_to=dst_ch)

                last_msg_id = msg_list[0].id
                last_channel_ids = update_last_channel_ids(channel_id, last_msg_id)

                # TODO: probably do this only for my subs.
                client.send_read_acknowledge(channel_id, msg_list)
                logger.debug(f"Channel {channel_id} is marked as read")

                logger.debug("\n")

        except Exception:
            logger.error(f"Channel {channel_id} was not processed", exc_info=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-level', type=str, default='INFO', required=False)
    args = parser.parse_args()
    log_level = args.log_level.upper()

    logging.basicConfig(
        # filename="MainClient.log",
        format='%(asctime)s %(module)s %(levelname)s: %(message)s',
        level=logging.WARNING,
        # level=log_level,
        datefmt='%a %d.%m.%Y %H:%M:%S',
        force=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    # logging.getLogger('src.filtering.filter').setLevel(log_level)
    logging.getLogger('src').setLevel(log_level)

    # if log_level != 'DEBUG':
    #     logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('telethon').setLevel(logging.ERROR)

    client = start_client('telefeed_client',
                          # bot_token=config.bot_token
                          )
    logger.info('telefeed_client started')

    while True:
        try:
            main(client)
            if log_level == 'DEBUG':
                wait = MAIN_LOOP_DELAY_SEC_DEBUG
            else:
                wait = MAIN_LOOP_DELAY_SEC_DEBUG
            # print("Waiting for", wait)
            time.sleep(wait)

        except KeyboardInterrupt:
            client.disconnect()
            exit()
        except:
            logger.error("While main loop failed", exc_info=True)
            time.sleep(30)
