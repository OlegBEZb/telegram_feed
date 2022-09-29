import argparse

from random import randint

import time
import logging
import coloredlogs

from typing import List

# These example values won't work. You must get your own api_id and
# api_hash from https://my.telegram.org, under API Development.

from telethon.sync import TelegramClient
from telethon.tl.types import MessageFwdHeader, PeerChannel
from telethon.tl.patched import Message
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.messages import GetPeerDialogsRequest, MarkDialogUnreadRequest
from telethon.tl.functions.messages import ForwardMessagesRequest, GetHistoryRequest
from telethon.tl.functions.channels import GetFullChannelRequest

from utils import OpenUpdateTime, SaveUpdateTime, SaveNewTime
from utils import check_copypaste, check_msg_list_for_adds, check_channel_correctness

import config


def chat_id2name(client: TelegramClient, chat_id):
    entity = client.get_input_entity(PeerChannel(chat_id))
    chat_full = client(GetFullChannelRequest(entity))
    if hasattr(chat_full, 'chats') and len(chat_full.chats) > 0:
        chat_title = chat_full.chats[0].title
        return chat_title


def get_source_channel_name_for_message(client: TelegramClient, msg: Message):
    if isinstance(msg.fwd_from, MessageFwdHeader):
        orig_name = chat_id2name(client, msg.fwd_from.from_id.channel_id)
        orig_date = msg.fwd_from.date
        fwd_to_name = chat_id2name(client, msg.chat_id)
        fwd_date = msg.date
    else:
        orig_name = chat_id2name(client, msg.chat_id)
        orig_date = msg.date
        fwd_to_name, fwd_date = None, None

    return orig_name, orig_date, fwd_to_name, fwd_date


def forward_msgs(client: TelegramClient, peer, msg_list: List[Message], peer_to_forward_to):

    logger.debug(f'messages before checking for advertisements: {len(msg_list)}')
    messages_checked_list = check_msg_list_for_adds(msg_list)
    logger.debug(f'messages after checking for advertisements: {len(messages_checked_list)}')

    # have to be more or less global and extended after every message forwarded to my channel
    my_channel_history = get_history(client=client, min_id=0,
                                     channel_id=config.MyChannel, limit=100)

    for msg in messages_checked_list:
        for my_msg in my_channel_history.messages:
            if check_copypaste(my_msg, msg):
                orig_name1, orig_date1, fwd_to_name1, fwd_date1 = get_source_channel_name_for_message(client, my_msg)
                orig_name2, orig_date2, fwd_to_name2, fwd_date2 = get_source_channel_name_for_message(client, msg)
                if fwd_to_name1 is None:  # channel 1 has it's own post
                    if fwd_to_name2 is None:  # channel 2 has it's own post
                        if orig_date1 > orig_date2:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{orig_name2}' before '{orig_name1}'")
                        else:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{orig_name1}' before '{orig_name2}'")
                    else:  # channel 2 has forwarded post
                        if orig_date1 > fwd_date2:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{fwd_to_name2}' (forwarded from '{orig_name2}') before '{orig_name1}'")
                        else:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{orig_name1}' before '{fwd_to_name2} (forwarded from '{orig_name2}')")
                else:  # channel 1 has forwarded post
                    if fwd_to_name2 is None:  # channel 2 has it's own post
                        if fwd_date1 > orig_date2:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{orig_name2}' before '{fwd_to_name1}' (forwarded from '{orig_name1}')")
                        else:
                            print(f"Message '{my_msg.message[:20]}...' was published by '{fwd_to_name1}' (forwarded from '{orig_name1}') before '{orig_name2}'")
                    else:  # channel 2 has forwarded post
                        if fwd_date1 > fwd_date2:
                            print(f"Message '{my_msg.message[:20]}...' was reposted by '{fwd_to_name2}' (from '{orig_name2}') before '{fwd_to_name1}' (from '{orig_name1}')")
                        else:
                            print(f"Message '{my_msg.message[:20]}...' was reposted by '{orig_name1}' (from '{fwd_to_name1}') before '{fwd_to_name2}' (from '{orig_name2}')")
                messages_checked_list.remove(msg)
                break
    logger.debug(f'after checking with the target channel history {len(messages_checked_list)}')

    grouped_msg_ids = list()  # https://github.com/LonamiWebs/Telethon/issues/1216
    msg_non_grouped = list()
    last_grouped_id = -1
    messages_checked_list.reverse()

    for msg in messages_checked_list:
        if log_level != 'DEBUG':
            time.sleep(randint(60, 120))  # not to send all the messages in bulk
        if msg.grouped_id is not None:
            if msg.grouped_id == last_grouped_id:
                grouped_msg_ids.append(msg.id)
            else:
                if msg_non_grouped:
                    send_msg(client, peer, msg_non_grouped, peer_to_forward_to)
                    msg_non_grouped = list()
                if grouped_msg_ids:  # in case of consequent groups
                    send_grouped(client, peer, grouped_msg_ids, peer_to_forward_to)
                    grouped_msg_ids = list()
                last_grouped_id = msg.grouped_id
                grouped_msg_ids.append(msg.id)
        else:
            if grouped_msg_ids:
                send_grouped(client, peer, grouped_msg_ids, peer_to_forward_to)
                grouped_msg_ids = list()
            msg_non_grouped.append(msg.id)

    if msg_non_grouped:
        send_msg(client, peer, msg_non_grouped, peer_to_forward_to)

    if grouped_msg_ids:
        send_grouped(client, peer, grouped_msg_ids, peer_to_forward_to)

        # client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        # print(f"{config.MyChannel} is marked as unread")
        #
        # dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
        # print('dialog.unread_count, dialog.unread_mark',
        #       dialog.unread_count, dialog.unread_mark)

    dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
    # print('at the end of forwarding\ndialog.unread_count, dialog.unread_mark',
    #       dialog.unread_count, dialog.unread_mark)

    return msg_list[0].id


def send_msg(client: TelegramClient, peer: str, msg_non_grouped: List[int], peer_to_forward_to: str):
    """

    :param client:
    :param peer: Anything entity-like will work if the library can find its Input version
    (e.g., usernames, Peer, User or Channel objects, etc.).
    :param msg_non_grouped: A list must be supplied.
    :param peer_to_forward_to:
    :return:
    """
    # print('sending msg')
    client(ForwardMessagesRequest(
        from_peer=peer,  # who sent these messages?
        id=msg_non_grouped,  # which are the messages?
        to_peer=peer_to_forward_to,  # who are we forwarding them to?
        with_my_score=True
    ))
    logger.debug('sent msg')

    # if we sent at least one message and the recipient is our channel,
    # we can mark this as unread (by default, read (!unread))
    if peer_to_forward_to == config.MyChannel:
        client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        logger.debug(f"{config.MyChannel} is marked as unread")


def send_grouped(client: TelegramClient, peer, grouped_ids, peer_to_forward_to):
    # print('sending group')
    client(ForwardMessagesRequest(
        from_peer=peer,
        id=grouped_ids,
        to_peer=peer_to_forward_to,
        with_my_score=True,
        # grouped=True
    ))
    logger.debug('sent group')

    # if we sent at least one message and the recipient is our channel,
    # we can mark this as unread (by default, read (!unread))
    if peer_to_forward_to == config.MyChannel:
        client(MarkDialogUnreadRequest(peer=peer_to_forward_to, unread=True))
        logger.info(f"{config.MyChannel} is marked as unread")

    return grouped_ids


def get_history(client: TelegramClient, min_id, channel_id, limit=100):
    messages = client(GetHistoryRequest(
        peer=channel_id,
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=limit,
        max_id=0,
        min_id=min_id,
        hash=0
    ))
    return messages


def get_last_msg_id(client: TelegramClient, channel_id):
    messages = get_history(client=client, min_id=0, channel_id=channel_id, limit=1)
    return messages.messages[0].id


def CheckCorrectlyPrivateLink(client: TelegramClient, req):
    try:
        client(CheckChatInviteRequest(hash=req))
        return True
    except:
        return False


def Subs2PrivateChat(client: TelegramClient, req):
    try:
        updates = client(ImportChatInviteRequest(req))
        client.edit_folder(updates.chats, 1)  # 1 is archived 0 unarchived
    except:
        print("already subs")


def main(client: TelegramClient):
    needSave = False
    channels = OpenUpdateTime()
    MyChannel = config.MyChannel

    for channel_id in channels:
        if channels[channel_id] == 0:  # last message_id is 0 because the channel is added manually
            print(f"Channel {channel_id} is just added and doesn't have the last message id")
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
            print(f"Channel {channel_id} is added with the last message id={last_msg_id}")
            channels = OpenUpdateTime()
        try:
            # print(f"Searching for new messages in channel: {channel_id} with the last msg_id {channels[channel_id]}")

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
                    messages = get_history(client=client, min_id=dialog.top_message - 1, channel_id=channel_id, limit=1)
                else:
                    logger.info(f"Channel {channel_id} has {dialog.unread_count} unread posts")
                    messages = get_history(client=client, min_id=dialog.read_inbox_max_id, channel_id=channel_id,
                                           limit=dialog.unread_count)

                msg_list = messages.messages

                # print(f"Found {len(msg_list)} messages in {messages.chats[0].title} (id={channel_id})")

                last_msg_id = forward_msgs(client=client, peer=channel_id, msg_list=msg_list,
                                           peer_to_forward_to=MyChannel)
                channels[channel_id] = last_msg_id
                # print("last_msg_id: " + str(last_msg_id))
                needSave = True

                # dialog = client(GetPeerDialogsRequest(peers=[config.MyChannel])).dialogs[0]
                # print('at the end of main\ndialog.unread_count, dialog.unread_mark',
                #       dialog.unread_count, dialog.unread_mark)

                client.send_read_acknowledge(channel_id, msg_list)
                logger.debug(f"Channel {channel_id} is marked as read")

        except Exception as e:
            logger.error(str(e))

    if needSave:
        SaveNewTime(channels)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-level', type=str, default='INFO', required=False)
    args = parser.parse_args()
    log_level = args.log_level.upper()

    logging.basicConfig(
        # filename="MainClient.log",
        format='%(asctime)s %(name)s %(levelname)s: %(message)s',
        level=logging.WARNING,
        datefmt='%Y-%m-%d %I:%M:%S')

    logger = logging.getLogger(__name__)
    if log_level != 'DEBUG':
        logging.getLogger('telethon').setLevel(logging.ERROR)
    logger.setLevel(log_level)
    coloredlogs.install(level=logging.INFO, logger=logger)

    api_id = config.api_id
    api_hash = config.api_hash
    isNotConnected = True
    logger.info("Start")

    connection_attempts = 1
    while isNotConnected:
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
                wait = 300
            # print("Waiting for", wait)
            time.sleep(wait)

        except KeyboardInterrupt:
            client.disconnect()
            exit()
        except Exception as e:
            print(str(e))
            logger.error(str(e))
            time.sleep(30)
