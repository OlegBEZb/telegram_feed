import asyncio
import os
import argparse
from copy import deepcopy

from random import randint

import time

import logging

from typing import List

from telethon import TelegramClient
from telethon.tl.types import TypeInputPeer, MessageActionGroupCall, MessageActionPinMessage
from telethon.tl.patched import Message
from telethon.tl.functions.messages import GetPeerDialogsRequest, ForwardMessagesRequest
from telethon.errors import (ChannelPrivateError, UsernameNotOccupiedError, MessageIdInvalidError, FloodWaitError,
                             ChatAdminRequiredError, ChatWriteForbiddenError, ChannelInvalidError)
from telethon.extensions import html


from src.common.utils import get_history, get_project_root, get_message_origins, get_entity
from src.common.database_utils import (get_last_channel_ids, update_last_channel_ids, get_feeds, log_messages,
                                       invert_feeds)
from src.common.database_utils import Channel

from src import config
from src.filtering.filter import Filter

from src.recommender.recommender import ContentBasedRecommender


# MAIN_LOOP_DELAY_SEC_DEBUG = 900  # TODO: add nightmode
MAIN_LOOP_DELAY_SEC_DEBUG = 1800
MAIN_LOOP_DELAY_SEC_INFO = 1800

MSG_POSTFIX_TEMPLATE = ("\n\n\n<em>Original post link: {post_link}</em>\n"
                        "<em>Forwarded and filtered by @smartfeed_bot</em>")  # powered by?


def send_group_if_non_empty(msg_list: List[Message], bot_client: TelegramClient, from_peer, peer_to_forward_to,
                            last_grouped_id=None, user_client: TelegramClient = None, send_not_forward=True):
    if msg_list:
        if last_grouped_id:  # then msg_list is a group
            logger.log(5, f"Sending group of {len(msg_list)} message(s) "
                          f"with last_grouped_id {last_grouped_id} to {peer_to_forward_to}")
        else:
            logger.log(5, f'Sending {len(msg_list)} non-grouped message(s) to {peer_to_forward_to}')

        try:
            if send_not_forward and all(m.media is None for m in msg_list):  # as original. TODO: remove the second part
            # if send_not_forward:  # as original
                asyncio.get_event_loop().run_until_complete(send_msg_list(msg_list=msg_list, bot_client=bot_client, peer_to_forward_to=peer_to_forward_to,
                              user_client=user_client))
            else:  # old option/regular forward
                forward_msg_by_id_list(client=bot_client, peer=from_peer, msg_ids_to_forward=[m.id for m in msg_list],
                                       peer_to_forward_to=peer_to_forward_to)
            msg_list = []

        # TODO: add send\forward to logger
        except ChannelInvalidError:
            logger.error(
                f"Invalid channel object (peer_to_forward_to={peer_to_forward_to}). Make sure to pass the right "
                f"types, for instance making sure that the "
                f"request is designed for channels or otherwise look for a different one more suited "
                f"(caused by GetChannelsRequest)")
        except ChatWriteForbiddenError:
            logger.error(
                f"{bot_client.get_me()} can't forward from {from_peer} to {peer_to_forward_to} (caused by ForwardMessagesRequest)")  # add the owner as well
        except ChatAdminRequiredError:
            logger.error("Chat admin privileges are required to do that in the specified chat (for example, to send a "
                         "message in a channel which is not yours), or invalid permissions used for the channel or group "
                         "(caused by ForwardMessagesRequest)")
        # telethon.errors.rpcerrorlist.MessageIdInvalidError probably on pinning a message
        except MessageIdInvalidError:
            logger.error("The specified message ID is invalid or you can't do that operation on such message.")
        except:
            logger.error(f'Was not able send the message to {peer_to_forward_to}', exc_info=True)

    return msg_list


def format_forwarded_msg_as_original(msg: Message, client: TelegramClient) -> Message:
    """
    Format a forwarded message as if it was sent from the original channel

    Parameters
    ----------
     msg : `Message`
        The message to be formatted
    client : `TelegramClient`
        The telegram client object

    Returns
    -------
    Message
        The message object after formatting as if it was sent from the original channel

    """
    orig_channel_id, orig_name, orig_date, fwd_to_channel_id, fwd_to_name, fwd_date = asyncio.get_event_loop().run_until_complete(
        get_message_origins(client, msg))
    orig_channel = Channel(channel_id=orig_channel_id, channel_name=orig_name, client=client)

    new_msg = deepcopy(msg)  # copies everything including media

    if orig_channel.is_public:
        post_link = orig_channel.link.replace('https://t.me/', 't.me/') + '/' + str(msg.id)
    elif not orig_channel.is_public:
        post_link = 't.me/c/' + str(orig_channel_id) + str(msg.id)
    else:
        post_link = 'unknown'
    postfix = MSG_POSTFIX_TEMPLATE.format(post_link=post_link)
    new_msg.message += postfix

    text, extra_entities = html.parse(new_msg.message)
    if new_msg.entities is None:
        new_msg.entities = extra_entities
    else:
        new_msg.entities += extra_entities
    new_msg.message = text

    return new_msg


async def send_msg_list(msg_list: List[Message], bot_client: TelegramClient, peer_to_forward_to: TypeInputPeer,
                  user_client: TelegramClient = None):
    """

    Parameters
    ----------
    msg_list
    bot_client
    peer_to_forward_to link or ID?

    Returns
    -------

    """
    for msg in msg_list:
        # TODO: add an additional step with forwarding to myself to allow using media. To func
        # TODO: Use get_messages and msg.forward_to
        if msg.media is not None:
            async with user_client:
                bot_entity = await user_client.get_entity('https://t.me/smartfeed_bot')
                # bot_entity = user_client.get_entity(-1005862458219)
                await user_client.send_message(entity=bot_entity, message='test')
                orig_channel_id, orig_name, orig_date, _, _, _ = await get_message_origins(user_client, msg)
                orig_channel_entity = await user_client.get_entity(orig_channel_id)
                # user_client.forward_messages(entity=bot_entity, messages=msg, from_peer=orig_channel_id)
                # await msg.forward_to('me')
                # await msg.forward_to(bot_entity)
                await user_client.forward_messages(entity=bot_entity, messages=msg, from_peer=orig_channel_entity)
                # user_client.forward_messages('https://t.me/smartfeed_bot', messages=msg)
            async with bot_client:
                msg = await bot_client.get_messages("https://t.me/Oleg_Litvinov_1997", #int('100'+str(config.my_id)),
                                              ids=msg.id)  # without ids, it may use getHistory, which bots cannot use. telethon.errors.rpcerrorlist.BotMethodInvalidError: The API access for bot users is restricted. The method you tried to invoke cannot be executed as a bot (caused by GetHistoryRequest)

                msg = await bot_client.get_messages("https://t.me/Oleg_Litvinov_1997",  # int('100'+str(config.my_id)),
                                              ids=1)

        new_msg = format_forwarded_msg_as_original(msg, bot_client)
        # from docs: If you want to “forward” a message without the forward header (the “forwarded from” text), you
        # should use send_message with the original message instead. This will send a copy of it.
        await bot_client.send_message(entity=peer_to_forward_to, message=new_msg.message, file=new_msg.media,
                                formatting_entities=new_msg.entities, link_preview=False)  # wrapper for functions.messages.SendMessageRequest


# TODO: add parameter send_as_mine/forward
# TODO: why link is used!? Switch to id
def group_and_forward_msgs(bot_client: TelegramClient, from_peer: TypeInputPeer, msg_list: List[Message],
                           peer_to_forward_to: TypeInputPeer, user_client: TelegramClient = None):
    """
    Forward messages in small pieces.

    :param bot_client:
    :param personal_client:
    :param from_peer:
    :param msg_list:
    :param peer_to_forward_to:
    :return:
    """
    grouped_msg_list = []  # https://github.com/LonamiWebs/Telethon/issues/1216
    non_grouped_msg_list = []
    last_grouped_id = -1

    for msg in reversed(msg_list):  # starting from the chronologically first
        # client.send_message(peer_to_forward_to, msg)
        if msg_is_action(msg=msg, client=bot_client, from_peer=from_peer, peer_to_forward_to=peer_to_forward_to):
            continue

        if msg.grouped_id is not None:  # the current message is a part of a group
            if msg.grouped_id == last_grouped_id:  # extending the same group
                grouped_msg_list.append(msg)
                logger.log(5, f"Group {msg.grouped_id} has one more message to be sent. Total size: {len(grouped_msg_list)}")
            else:
                grouped_msg_list, non_grouped_msg_list = resolve_and_send_groups(bot_client=bot_client,
                                                                                 grouped_msg_list=grouped_msg_list,
                                                                                 non_grouped_msg_list=non_grouped_msg_list,
                                                                                 from_peer=from_peer,
                                                                                 peer_to_forward_to=peer_to_forward_to,
                                                                                 last_grouped_id=last_grouped_id,
                                                                                 user_client=user_client)
                last_grouped_id = msg.grouped_id
                grouped_msg_list.append(msg)
                logger.log(5, f"Group {msg.grouped_id} has one more message to be sent. "
                              f"Total size: {len(grouped_msg_list)}")
        else:  # the current message is a single message
            grouped_msg_list = send_group_if_non_empty(msg_list=grouped_msg_list, bot_client=bot_client, from_peer=from_peer,
                                                       peer_to_forward_to=peer_to_forward_to,
                                                       last_grouped_id=last_grouped_id,
                                                       user_client=user_client)
            non_grouped_msg_list.append(msg)
            logger.log(5, f"Non-grouped messages list is extended. Total size: {len(non_grouped_msg_list)}")

    _, _ = resolve_and_send_groups(bot_client=bot_client,
                                   grouped_msg_list=grouped_msg_list,
                                   non_grouped_msg_list=non_grouped_msg_list,
                                   from_peer=from_peer,
                                   peer_to_forward_to=peer_to_forward_to,
                                   last_grouped_id=last_grouped_id,
                                   user_client=user_client)


def resolve_and_send_groups(bot_client, grouped_msg_list, non_grouped_msg_list, from_peer, peer_to_forward_to,
                            last_grouped_id, user_client: TelegramClient = None):
    non_grouped_msg_list = send_group_if_non_empty(msg_list=non_grouped_msg_list, bot_client=bot_client,
                                                   from_peer=from_peer,
                                                   peer_to_forward_to=peer_to_forward_to,
                                                   last_grouped_id=None,
                                                   user_client=user_client)
    grouped_msg_list = send_group_if_non_empty(msg_list=grouped_msg_list, bot_client=bot_client,
                                               from_peer=from_peer, peer_to_forward_to=peer_to_forward_to,
                                               last_grouped_id=last_grouped_id,
                                               user_client=user_client)
    return grouped_msg_list, non_grouped_msg_list


def msg_is_action(msg, client, from_peer, peer_to_forward_to):
    try:
        # TODO: check if regular messages have action. Looks like not
        if isinstance(msg.action, (MessageActionGroupCall, MessageActionGroupCall)):
            if msg.action.duration is None:
                logger.info(f"{from_peer} started a call")
                client.send_message(peer_to_forward_to, f"{from_peer} started a call")
            else:
                logger.info(f"{from_peer} ended a call")
                client.send_message(peer_to_forward_to, f"{from_peer} ended a call")
            return True
        if isinstance(msg.action, MessageActionPinMessage):
            logger.info(f"{from_peer} pinned a message")
            client.send_message(peer_to_forward_to, f"{from_peer} pinned a message")
            return True
        return False
    except ChatWriteForbiddenError:
        logger.error(f"{client.get_me()} can't forward from {from_peer} to {peer_to_forward_to} "
                     f"(caused by ForwardMessagesRequest)")  # add the owner as well


def forward_msg_by_id_list(client: TelegramClient, peer: TypeInputPeer, msg_ids_to_forward: List[int],
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

    logger.log(5, f'forwarding msg to {peer_to_forward_to}')
    client(ForwardMessagesRequest(
        from_peer=peer,  # who sent these messages?
        id=msg_ids_to_forward,  # which are the messages? = grouped_ids
        to_peer=peer_to_forward_to,  # who are we forwarding them to?
        with_my_score=True
    ))
    logger.log(5, f'forwawrded msg ids: {msg_ids_to_forward} to {peer_to_forward_to}')


# TODO: simplify function
def main(user_client: TelegramClient, bot_client: TelegramClient, recommender):
    last_channel_ids = get_last_channel_ids()
    feeds = get_feeds()  # which dst channel reads what source channels
    scr2dst = invert_feeds(feeds, user_client)

    for src_ch, dst_ch_list in scr2dst.items():  # pool of all channels for all users
        # if src_ch.id not in [-1001099860397, -1001288791823]:  # rbc and love death
        #     continue
        # TODO: resurrect it back. When the channel is just added with 0 from default dict, give some small portion of
        # content. Not 100
        # if channels[src_ch.link] == 0:  # last message_id is 0 because the channel is added manually
        #     logger.debug(f"Channel {src_ch.link} is just added and doesn't have the last message id")
        #     # if src_ch.link.find("t.me/joinchat") != -1:
        #     #     ch = src_ch.link.split("/")
        #     #     req = ch[len(ch)-1]
        #     #     isCorrect = CheckCorrectlyPrivateLink(client, req)
        #     #     if not isCorrect:
        #     #         channels.pop(src_ch.link)
        #     #         print("Removing incorrect channel")
        #     #         break
        #     #     Subs2PrivateChat(client, req)
        #     channel_checked = check_channel_correctness(src_ch.link)
        #     if channel_checked == 'error':
        #         req = src_ch.link.split("/")[-1]
        #         if not CheckCorrectlyPrivateLink(client, req):
        #             channels.pop(src_ch.link)
        #             print(f"Removing incorrect channel: {src_ch.link}")
        #             break
        #         Subs2PrivateChat(client, req)
        #
        #     channels = OpenUpdateTime()
        try:
            logger.log(5, f"Searching for new messages in channel: {src_ch!r} with the last msg_id {last_channel_ids[src_ch.id]}")

            messages = check_new_channel_messages(src_ch=src_ch, last_channel_ids=last_channel_ids, client=user_client)
            if messages is not None:
                # time.sleep(randint(5, 10))
                msg_list = messages.messages  # by default their order is descending (recent to old)
                # logger.debug(f"Found {len(msg_list)} message(s) in '{messages.chats[0].title}' ({src_ch.link})")
                logger.debug(f"Found {len(msg_list)} message(s) in '{src_ch!r})")

                # TODO: Here recommender system should act and decide to which users send the content
                for dst_ch in dst_ch_list:
                    # if dst_ch.id not in [-1001504355267, -1001851389727]:  # my channels
                    #     continue
                    messages_checked_list = select_messages_for_dst_channel(msg_list=msg_list,
                                                                            src_ch=src_ch,
                                                                            dst_ch=dst_ch,
                                                                            recommender=recommender,
                                                                            user_client=user_client)

                    if dst_ch.is_public:
                        # may be utilised with an "empty" bot as link is enough?
                        # group_and_forward_msgs(client=bot_client, from_peer=src_ch.link, msg_list=messages_checked_list,
                        #                        peer_to_forward_to=dst_ch.link)  # TODO: switch to .id as well?
                        group_and_forward_msgs(bot_client=bot_client, from_peer=src_ch.id, msg_list=messages_checked_list,
                                               peer_to_forward_to=dst_ch.id, user_client=user_client)
                    else:  # TODO: reduce this branch proving that link is not needed
                        group_and_forward_msgs(bot_client=bot_client, from_peer=src_ch.link, msg_list=messages_checked_list,
                                               peer_to_forward_to=dst_ch.id, user_client=user_client)

                # TODO: this increment probably has to be performed anyway even in case of fail
                last_msg_id = msg_list[0].id
                last_channel_ids = update_last_channel_ids(src_ch.id, last_msg_id)

                # TODO: probably do this only for my subs.
                with user_client:
                    user_client.send_read_acknowledge(src_ch.id, msg_list)  # TODO: got flood by ResolveUsernameRequest -> switch to id?
                    logger.log(8, f"Channel {src_ch.link} is marked as read for me({client.get_me().id})")

                logger.debug("\n")

        except:
            # TODO: process if channel doesn't exist. delete and notify
            logger.error(f"Channel {src_ch} was not processed", exc_info=True)

        # time.sleep(randint(30, 60))
        time.sleep(2)


def select_messages_for_dst_channel(msg_list: List[Message], src_ch: Channel, dst_ch: Channel,
                                    recommender, user_client: TelegramClient) -> List[Message]:
    try:
        # TODO: perform history check later wrt the dst channel and it's rb list
        with user_client:
            # logger.error('HISTORY IS NOT CHECKED')
            filter_component = Filter(rule_base_check=True, history_check=True, client=user_client,
                                      dst_ch=dst_ch, use_common_rules=True,
                                      postfix_template_to_ignore=MSG_POSTFIX_TEMPLATE)
            messages_checked_list, filtering_details = filter_component.filter_messages(msg_list)

        for msg in messages_checked_list:
            with user_client:
                recommend_prob = recommender.predict_proba(msg, client=user_client,
                                                           user_channel_link=dst_ch.link)

        with user_client:  # TODO: swich to async with?
            asyncio.get_event_loop().run_until_complete(log_messages(
                client=user_client,
                msg_list_before=msg_list,
                filtering_details=filtering_details,
                src_channel_id=src_ch.id,
                src_channel_link=src_ch.link,
                src_channel_name=src_ch.name,
                user_channel_id=dst_ch.id,
                user_channel_link=dst_ch.link,
                user_channel_name=dst_ch.name))
    except:
        logger.error('Failed to perform message selection. Sending as they are', exc_info=True)
        messages_checked_list = msg_list
    return messages_checked_list


def check_new_channel_messages(src_ch, last_channel_ids, client):
    try:
        with client:
            # solution based on the last index mentioned in the json. We can't just check if there are some unread
            # messages because for that you have to be subscribed to the channel. Otherwise, you must anchor yourself to
            # some message ID in the past - this is what we do. For the just added channel with the default last
            # message id of 0, the batch will be large. But after disconnections this limit of 100 may be insufficient
            # and there will be gaps
            # peer=InputPeerChannel(entity_id, entity_hash)
            messages = None
            messages = get_history(client=client, min_id=last_channel_ids[src_ch.id], peer=src_ch.id, limit=30)
            if len(messages.messages) == 0:
                try:
                    # solution based on telegram dialog fields
                    dialog = client(GetPeerDialogsRequest(peers=[src_ch.id])).dialogs[0]
                    # there are naturally unread messages or the channel is marked as unread
                    # it's important that for channels on which you are not subscribed, both unread_count and unread_mask
                    # don't work
                except FloodWaitError as e:
                    logger.error(
                        f'Got FloodWaitError cause by GetPeerDialogsRequest. Have to sleep {e.seconds} seconds / {e.seconds / 60:.1f} minutes / '
                        f'{e.seconds / 60 / 60:.1f} hours')

                # TODO: add marked unread manually to the logs
                if dialog.unread_count or dialog.unread_mark:
                    if dialog.unread_mark:
                        logger.info(f"Channel {src_ch} is marked as unread manually")
                        # if fetched message.grouped_id is not None, fetch until group changes and then send
                        messages = get_history(client=client, min_id=dialog.top_message - 1, peer=src_ch.id, limit=1)
                    else:  # this should not be triggered and has to be removed
                        logger.info(f"Channel {src_ch} has {dialog.unread_count} unread posts")
                        messages = get_history(client=client, min_id=dialog.read_inbox_max_id, peer=src_ch.id,
                                               limit=dialog.unread_count)
    # TODO: remove channel from database or fetch the recent info
    except UsernameNotOccupiedError:
        logger.error(f"{src_ch} is not found.\nConsider removing from all readlists", exc_info=True)
        # remove_source_channel()
        return None
    except ChannelPrivateError:
        logger.error('Consider removing from all readlists')
        # remove_source_channel()
        return None
    except FloodWaitError as e:
        # TODO: it looks like only some of the channels are blocked -> do not fetch them but all the others
        # time.sleep(e.seconds)
        raise
    except:
        logger.error(f'Unknown fail in get_history with {src_ch}')
        return None

    if messages is None or len(messages.messages) == 0:
        return None
    return messages


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-level', type=str, default='INFO', required=False)
    args = parser.parse_args()
    log_level = args.log_level.upper()

    logging.basicConfig(
        # filename="main_feed.log",
        format='%(asctime)s %(module)s %(levelname)s: %(message)s',
        # level=logging.WARNING,
        # level=log_level,
        level=logging.DEBUG,
        datefmt='%a %d.%m.%Y %H:%M:%S',
        force=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    # logging.getLogger('src.filtering.filter').setLevel(log_level)
    logging.getLogger('src').setLevel(log_level)

    # if log_level != 'DEBUG':
    #     logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('telethon').setLevel(logging.ERROR)

    user_client_path = os.path.join(get_project_root(), 'src/telefeed_client')
    client = TelegramClient(user_client_path, config.api_id, config.api_hash)
    logger.info(f'{user_client_path} created (not started)')

    # TODO: check if may be used the regular bot client from src.bot import bot_client
    #  the same bot may not be used as it may process sth in the simultaneously working main_bot_cli process
    #  and the process in main_bot_cli should be listening for the updates constantly
    forwarding_bot_path = os.path.join(get_project_root(), f'src/bot_for_feed_{config.bot_id}')
    # forwarding_bot_path = os.path.join(get_project_root(), 'src/bot')
    forwarding_bot_client = TelegramClient(forwarding_bot_path, config.api_id, config.api_hash).start(
        bot_token=config.bot_token)
    logger.info(f'{forwarding_bot_path} created (not started)')

    cb_recommender = ContentBasedRecommender()
    cb_recommender.load(os.path.join(get_project_root(), 'src/recommender/'))
    logger.info('ContentBasedRecommender is loaded')

    while True:
        try:
            main(user_client=client, bot_client=forwarding_bot_client, recommender=cb_recommender)
            if log_level == 'DEBUG':
                MAIN_LOOP_DELAY_SEC = MAIN_LOOP_DELAY_SEC_DEBUG
            else:
                MAIN_LOOP_DELAY_SEC = MAIN_LOOP_DELAY_SEC_INFO
            print(f"Waiting for {MAIN_LOOP_DELAY_SEC} sec / {MAIN_LOOP_DELAY_SEC/60} min for the main loop")
            time.sleep(MAIN_LOOP_DELAY_SEC)

        except KeyboardInterrupt:
            client.disconnect()
            exit()
        except:
            logger.error("While main loop failed", exc_info=True)
            time.sleep(30)
