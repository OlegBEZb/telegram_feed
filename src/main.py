import argparse

from random import randint

import time

import logging

from typing import List

# These example values won't work. You must get your own api_id and
# api_hash from https://my.telegram.org, under API Development.

from telethon.sync import TelegramClient
from telethon.tl.types import TypeInputPeer
from telethon.tl.patched import Message
from telethon.tl.functions.messages import GetPeerDialogsRequest, MarkDialogUnreadRequest
from telethon.tl.functions.messages import ForwardMessagesRequest

from src.utils import OpenUpdateTime, SaveUpdateTime, SaveNewTime, get_history, CheckCorrectlyPrivateLink, \
    Subs2PrivateChat
from src.utils import check_channel_correctness

from src import config
from src.filtering.filter import Filter


def forward_msgs(client: TelegramClient, peer: TypeInputPeer, msg_list: List[Message], peer_to_forward_to: TypeInputPeer):
    grouped_msg_ids = list()  # https://github.com/LonamiWebs/Telethon/issues/1216
    msg_non_grouped = list()
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
                    msg_non_grouped = list()
                if grouped_msg_ids:  # in case of consequent groups
                    logger.debug(
                        f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
                    send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)
                    grouped_msg_ids = list()
                last_grouped_id = msg.grouped_id
                grouped_msg_ids.append(msg.id)
                logger.debug(
                    f"Group {msg.grouped_id} has one more message to be sent. Total size:{len(grouped_msg_ids)}")
        else:  # the current message is a single message
            if grouped_msg_ids:
                logger.debug(f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
                send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)
                grouped_msg_ids = list()
            msg_non_grouped.append(msg.id)
            logger.debug(f"Non-grouped messages list is extended. Total size: {len(msg_non_grouped)}")

    if msg_non_grouped:
        logger.debug(f'Sending {len(msg_non_grouped)} non-grouped message(s)')
        send_msg(client, peer, msg_non_grouped, peer_to_forward_to)

    if grouped_msg_ids:
        logger.debug(f"Sending group of {len(grouped_msg_ids)} message(s) with last_grouped_id {last_grouped_id}")
        send_msg(client, peer, grouped_msg_ids, peer_to_forward_to)

        # client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        # print(f"{config.MyChannel} is marked as unread")
        #
        # dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
        # print('dialog.unread_count, dialog.unread_mark',
        #       dialog.unread_count, dialog.unread_mark)

    dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
    # print('at the end of forwarding\ndialog.unread_count, dialog.unread_mark',
    #       dialog.unread_count, dialog.unread_mark)


def send_msg(client: TelegramClient, peer, msg_ids_to_forward: List[int], peer_to_forward_to: str):
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
        time.sleep(randint(60, 120))  # not to send all the messages in bulk
    logger.debug('sending msg')
    client(ForwardMessagesRequest(
        from_peer=peer,  # who sent these messages?
        id=msg_ids_to_forward,  # which are the messages? = grouped_ids
        to_peer=peer_to_forward_to,  # who are we forwarding them to?
        with_my_score=True
    ))
    logger.debug(f'sent msg ids: {msg_ids_to_forward}')

    # if we sent at least one message and the recipient is our channel,
    # we can mark this as unread (by default, read (!unread))
    if peer_to_forward_to == config.MyChannel:
        client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        logger.debug(f"{config.MyChannel} is marked as unread")


def get_last_msg_id(client: TelegramClient, channel_id):
    messages = get_history(client=client, peer=channel_id, limit=1)
    return messages.messages[0].id


def main(client: TelegramClient):
    needSave = False
    channels = OpenUpdateTime()
    MyChannel = config.MyChannel

    filter = Filter(rule_base_check=True, history_check=True, client=client)

    for channel_id in channels:
        if channels[channel_id] == 0:  # last message_id is 0 because the channel is added manually
            logger.debug(f"Channel {channel_id} is just added and doesn't have the last message id")
            # if channel_id.find("t.me/joinchat") != -1:
            #     ch = channel_id.split("/")
            #     req = ch[len(ch)-1]
            #     isCorrect = CheckCorrectlyPrivateLink(client, req)
            #     if not isCorrect:
            #         channels.pop(channel_id)
            #         print("Removing incorrect channel")
            #         break
            #     Subs2PrivateChat(client, req)
            channel_checked = check_channel_correctness(channel_id)
            if channel_checked == 'error':
                req = channel_id.split("/")[-1]
                if not CheckCorrectlyPrivateLink(client, req):
                    channels.pop(channel_id)
                    print(f"Removing incorrect channel: {channel_id}")
                    break
                Subs2PrivateChat(client, req)

            last_msg_id = get_last_msg_id(client, channel_id)
            SaveUpdateTime(key=channel_id, LastMsg_id=last_msg_id)
            logger.debug(f"Channel {channel_id} is added with the last message id={last_msg_id}")
            channels = OpenUpdateTime()
        try:
            logger.log(5, f"Searching for new messages in channel: {channel_id} with the last msg_id {channels[channel_id]}")

            # solution based on the last index mentioned in the json
            # msg_list = GetHistory(client=client, min=channels[channel_id], channel_id=channel_id)
            # if len(msg_list) > 0:

            # solution based on telegram dialog fields
            dialog = client(GetPeerDialogsRequest(peers=[channel_id])).dialogs[0]
            # there are naturally unread messages or the channel is marked as unread
            # it's important that for channels on which you are not subscribed, both unread_count and unread_mask don't work
            if dialog.unread_count or dialog.unread_mark:
                if dialog.unread_mark:
                    logger.info(f"Channel {channel_id} is marked as unread manually")
                    # if fetched message.grouped_id is not None, fetch until group changes and then send
                    messages = get_history(client=client, min_id=dialog.top_message - 1, peer=channel_id, limit=1)
                else:
                    logger.info(f"Channel {channel_id} has {dialog.unread_count} unread posts")
                    messages = get_history(client=client, min_id=dialog.read_inbox_max_id, peer=channel_id,
                                           limit=dialog.unread_count)

                msg_list = messages.messages  # by default their order is descending (recent to old)
                last_msg_id = msg_list[0].id
                channels[channel_id] = last_msg_id
                # print("last_msg_id: " + str(last_msg_id))
                needSave = True

                # print(f"Found {len(msg_list)} messages in {messages.chats[0].title} (id={channel_id})")
                messages_checked_list = filter.filter_messages(msg_list)
                logger.debug(f'Before filtering: {len(msg_list)}. After {len(messages_checked_list)}')

                forward_msgs(client=client, peer=channel_id, msg_list=messages_checked_list,
                             peer_to_forward_to=MyChannel)

                # dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
                # print('at the end of main\ndialog.unread_count, dialog.unread_mark',
                #       dialog.unread_count, dialog.unread_mark)

                client.send_read_acknowledge(channel_id, msg_list)
                logger.debug(f"Channel {channel_id} is marked as read")

        except Exception as e:
            logger.error(str(e), exc_info=True)

    if needSave:
        SaveNewTime(channels)


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
        datefmt='%Y-%m-%d %I:%M:%S',
        force=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    logging.getLogger('src.filtering.filter').setLevel(log_level)

    # if log_level != 'DEBUG':
    #     logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('telethon').setLevel(logging.ERROR)

    api_id = config.api_id
    api_hash = config.api_hash
    isNotConnected = True
    logger.info("Start")

    connection_attempts = 1
    while isNotConnected:  # TODO: make a func for that
        try:
            logger.debug(f"Connection attempt: {connection_attempts}")
            client = TelegramClient('telefeed_client', api_id, api_hash)
            client.start()
            logger.debug('TelegramClient is started\n')
            isNotConnected = False
        except Exception as e:
            connection_attempts += 1
            logger.error(str(e))
            time.sleep(30)

    while True:
        try:
            main(client)
            if log_level == 'DEBUG':
                wait = 10
            else:
                wait = 600
            # print("Waiting for", wait)
            time.sleep(wait)

        except KeyboardInterrupt:
            client.disconnect()
            exit()
        except Exception as e:
            print(str(e))
            logger.error(str(e))
            time.sleep(30)
