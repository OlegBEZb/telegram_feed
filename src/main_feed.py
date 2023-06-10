import asyncio
import os
import re
import argparse
from random import randint
from copy import deepcopy
import time
import datetime

import logging

from typing import List, Dict

from telethon import TelegramClient
from telethon.tl.types import (TypeInputPeer, MessageActionGroupCall, MessageActionPinMessage,
                               MessageActionGroupCallScheduled, MessageMediaWebPage, WebPage, WebPageEmpty,
                               MessageMediaInvoice)
from telethon.tl.patched import Message
from telethon.tl.functions.messages import GetPeerDialogsRequest, ForwardMessagesRequest
from telethon.errors import (ChannelPrivateError, UsernameNotOccupiedError, MessageIdInvalidError, FloodWaitError,
                             ChatAdminRequiredError, ChatWriteForbiddenError, ChannelInvalidError, MediaEmptyError,
                             MediaCaptionTooLongError, MessageTooLongError, EntityBoundsInvalidError,
                             ChatForwardsRestrictedError)
from telethon.extensions import html


from src.common.utils import get_history, get_message_origins
from src.common.get_project_root import get_project_root
from src.common.database_utils import (get_last_channel_ids, get_last_bot_id, save_last_bot_ids,
                                       update_last_channel_ids, get_feeds, log_messages,
                                       invert_feeds, get_channel_owner)
from src.common.channel import Channel

from src import config
from src.filtering.filter import Filter

from src.recommender.recommender import ContentBasedRecommender


# MAIN_LOOP_DELAY_SEC_DEBUG = 900  # TODO: add nightmode
MAIN_LOOP_DELAY_SEC_DEBUG = 1800
MAIN_LOOP_DELAY_SEC_INFO = 1800

MSG_POSTFIX_TEMPLATE = ("\n\n\n<em>Original post link: {post_link}</em>\n"
                        "<em>Forwarded and filtered by @smartfeed_bot</em>")  # powered by?


def send_group_if_non_empty(msg_list: List[Message], bot_client: TelegramClient, from_peer, peer_to_forward_to,
                            last_grouped_id=None, user_client: TelegramClient = None, send_not_forward=False):
    if msg_list:
        if last_grouped_id:  # then msg_list is a group
            logger.log(5, f"Sending group of {len(msg_list)} message(s) "
                          f"with last_grouped_id {last_grouped_id} to {peer_to_forward_to}")
        else:
            logger.log(5, f'Sending {len(msg_list)} non-grouped message(s) to {peer_to_forward_to}')

        try:
            if last_grouped_id:
                if len(msg_list[0].message) < 900:
                    send_not_forward = True
            else:
                if all(len(msg.message) < 900 for msg in msg_list):  # TODO: it's better to do this on a message level
                    send_not_forward = True

            if send_not_forward:  # as original
                logger.log(5, "The first group message is (or all non-grouped messages are) less than 900 symbols. There is space to add my signature")
            # if send_not_forward:  # as original
                asyncio.get_event_loop().run_until_complete(send_msg_list(msg_list=msg_list, bot_client=bot_client,
                                                                          peer_to_forward_to=peer_to_forward_to,
                                                                          last_grouped_id=last_grouped_id,
                                                                          user_client=user_client))
            else:  # old option/regular forward
                logger.log(5, "The first group message is (or all non-grouped messages are) more than 900 symbols. Just forward")
                forward_msg_by_id_list(client=bot_client, peer=from_peer, msg_ids_to_forward=[m.id for m in msg_list],
                                       peer_to_forward_to=peer_to_forward_to)
            msg_list = []

        except ChannelPrivateError:
            logger.error(f"Unable to send to peer_to_forward_to={peer_to_forward_to}. The channel specified is private "
                         "and you lack permission to access it. Another reason may be that you were banned from it "
                         "(caused by ForwardMessagesRequest)")
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
        except ChatForwardsRestrictedError:
            # TODO: this have to be registred properly. rn messages have forward status
            logger.error(f"{from_peer} restricted the option to forward messages")
        except:
            logger.error(f'Was not able send the message to {peer_to_forward_to}', exc_info=True)

    return msg_list


def format_forwarded_msg_as_original(msg: Message, orig_channel: Channel, original_msg_id) -> Message:
    """
    Format a forwarded message as if it was sent from the original channel

    Parameters
    ----------
     msg : `Message`
        The message to be formatted

    Returns
    -------
    Message
        The message object after formatting as if it was sent from the original channel

    """
    try:
        # without that copying doesn't work
        msg._client = None
        if msg._forward:
            msg._forward._client = None
        new_msg = deepcopy(msg)
    except:
        logger.error(f'Unable to remove clients from message\n{msg.stringify()}')

    if orig_channel.is_public == True:
        post_link = orig_channel.link.replace('https://t.me/', 't.me/') + '/' + str(original_msg_id)
    elif orig_channel.is_public == False:
        post_link = 't.me/c/' + str(orig_channel.id) + '/' + str(original_msg_id)
    else:
        post_link = 'unknown'

    new_msg.message = remove_original_channel_signature(new_msg.message)

    postfix = MSG_POSTFIX_TEMPLATE.format(post_link=post_link)
    new_msg.message += postfix

    text, extra_entities = html.parse(new_msg.message)
    new_msg.message = text
    if new_msg.entities is None:
        new_msg.entities = extra_entities
    else:
        new_msg.entities += extra_entities

    return new_msg


def remove_original_channel_signature(msg: str):
    # TODO: check potential bug of a removed link at the end of the post below
    #  Доклад
    #
    # @ai_newz
    #
    # replaces other channel signature at the end of the message (should be without entities)
    # but anyway MessageEntityMention remains. Is this a problem?
    # TODO: move this action to the filtering stage as well to be less dependent on copypasted material
    if re.search(r"\n+@[a-z_]+\n*$", msg):  # TODO: fix also 👉@computer_science_and_programming and https://t.me/+Qm9PbhU6Lf0h5wsm
        msg = re.sub(r"\n+@[a-z_]+\n*$", "", msg)
    return msg


async def send_msg_list(msg_list: List[Message], bot_client: TelegramClient, peer_to_forward_to: TypeInputPeer,
                        last_grouped_id=None,
                        user_client: TelegramClient = None):
    """

    Parameters
    ----------
    msg_list : List[Message]
        List of 1+ messages. They may be grouped (same grouped_id) or not.
    bot_client
    peer_to_forward_to link or ID?

    Returns
    -------

    """
    # TODO: check A Bot API-like ``file_id``. You can convert previously
    #                   sent media to file IDs for later reusing with
    #                   `telethon.utils.pack_bot_file_id`.
    if last_grouped_id:
        # media is MessageMediaPhoto. the message with the smallest ID has the message field aka caption
        # like here https://stackoverflow.com/questions/64111232/python-telethon-send-album
        # group comes with ascending msg_id
        async with user_client:
            orig_channel, _, original_msg_id, _, _, _ = await get_message_origins(user_client, msg_list[0])

        album_msg_list = []
        for msg in msg_list:
            album_msg = await ensure_media_access(msg, user_client, bot_client, orig_channel.id)
            album_msg_list.append(album_msg)

        async with bot_client:
            new_msg = format_forwarded_msg_as_original(album_msg_list[0], orig_channel, original_msg_id)  # maybe it should be album_list but for some reason 0th album message doesn't have text
            try:
                await bot_client.send_message(entity=peer_to_forward_to,
                                              message=new_msg.message,
                                              file=album_msg_list,  # event.messages is a List - meaning we're sending an album
                                              formatting_entities=new_msg.entities,
                                              link_preview=True)  # wrapper for functions.messages.SendMessageRequest
            except MediaEmptyError:
                logger.error(f"Unable to send message to {peer_to_forward_to}\n{new_msg.stringify()}\n")
            except MediaCaptionTooLongError:  # 1024
                logger.error(f"Unable to send too long media caption to {peer_to_forward_to} "
                             f"with msg len: {len(new_msg.message)} (caused by SendMultiMediaRequest)\n"
                             f"last_grouped_id: {last_grouped_id}\n{new_msg}")
            except EntityBoundsInvalidError:
                logger.error(f"Some of provided entities have invalid bounds (length is zero or out of the boundaries "
                             f"of the string) (caused by SendMultiMediaRequest)\n{new_msg.message}\n{new_msg.entities}")

    else:  # if the messages are independent, process one by one with a common .message extension
        for msg in msg_list:
            async with user_client:
                orig_channel, _, original_msg_id, _, _, _ = await get_message_origins(user_client, msg)

            msg = await ensure_media_access(msg, user_client, bot_client, orig_channel.id)

            # TODO: groups are not together
            async with bot_client:
                new_msg = format_forwarded_msg_as_original(msg, orig_channel, original_msg_id)
                # from docs: If you want to “forward” a message without the forward header (the “forwarded from” text),
                # you should use send_message with the original message instead. This will send a copy of it.
                media = new_msg.media
                link_preview = False
                if isinstance(new_msg.media, MessageMediaWebPage):
                    if isinstance(new_msg.media.webpage, WebPage):  # Webpage preview
                        media = new_msg.media.webpage.document or new_msg.media.webpage.photo
                    elif isinstance(new_msg.media.webpage, WebPageEmpty):
                        media = None  # Bots can't access web previews. TODO: create myself?
                        link_preview = True
                try:
                    # TODO: fix TypeError: Cannot use <telethon.tl.types.MessageMediaPoll object at 0x125b8a8b0> as file
                    await bot_client.send_message(entity=peer_to_forward_to,
                                                  message=new_msg.message,
                                                  file=media,  # TODO: make this a list of all the messages in a group
                                                  formatting_entities=new_msg.entities,
                                                  link_preview=link_preview)  # wrapper for functions.messages.SendMessageRequest
                except MediaEmptyError:
                    logger.error(f"Unable to send message to {peer_to_forward_to}\n{new_msg.stringify()}\n"
                                 f"with media\n{media.stringify()}\n(caused by SendMediaRequest)")
                except MessageTooLongError:
                    # TODO: check according to the publically available limitations?
                    logger.error(f"Unable to send too long message to {peer_to_forward_to} "
                                 f"with msg len: {len(new_msg.message)} (caused by SendMediaRequest)")
                except MediaCaptionTooLongError:  # 1148
                    logger.error(f"Unable to send too long media caption to {peer_to_forward_to} "
                                 f"with msg len: {len(new_msg.message)} (caused by SendMediaRequest)\n{new_msg}")
                except EntityBoundsInvalidError:
                    logger.error(
                        f"Some of provided entities have invalid bounds (length is zero or out of the boundaries "
                        f"of the string) (caused by SendMultiMediaRequest)\n{new_msg.message}\n{new_msg.entities}")


async def ensure_media_access(msg, user_client, bot_client, orig_channel_id):
    async def sync_bot_last_msg_id():
        # logger.error('Bot chat with the user is out of sync. Syncing')

        now = datetime.datetime.now(datetime.timezone.utc)
        diff_seconds = 999999
        tolerance = 10
        last_msg = None

        last_expected_id = get_last_bot_id()
        last_actual_id = last_expected_id
        while diff_seconds > 60 or tolerance > 0:
            last_expected_id += 1
            tolerance -= 1

            bot_from_user_msg = await bot_client.get_messages(config.my_id, ids=last_expected_id)  # in debug mode failed with 'NoneType' object has no attribute 'my_id'
            if bot_from_user_msg:
                # print(i, bot_from_user_msg.date)
                # print(bot_from_user_msg)
                last_actual_id = last_expected_id
                last_msg = bot_from_user_msg
                diff_seconds = (now - last_msg.date).seconds

                # we always check 10 next messages after the existing one
                tolerance = 10


        if last_actual_id % 5 == 0:
            logger.info(f'Last id and UTC date in the bot chat: {last_actual_id}, {last_msg.date}')
        save_last_bot_ids(last_actual_id)
        return last_msg, last_actual_id

    if msg.media is not None:
        async with user_client:
            bot_entity = await user_client.get_input_entity(config.bot_id)
            await user_client.forward_messages(entity=bot_entity, messages=msg, from_peer=orig_channel_id)
        async with bot_client:
            # bot_last_id = get_last_bot_id() + 1  # as we have just sent another one
            # msg = await bot_client.get_messages(config.my_id, ids=bot_last_id)
            # if msg:
            #     save_last_bot_ids(bot_last_id)
            # else:
            #     msg, last_actual_id = await sync_bot_last_msg_id()  # it's a force sync of the bot chat
            msg, last_actual_id = await sync_bot_last_msg_id()  # for debugging
    return msg


# TODO: add parameter send_as_mine/forward
# TODO: why link is used!? Switch to id
def group_and_forward_msgs(bot_client: TelegramClient, src_ch: Channel, msg_list: List[Message],
                           peer_to_forward_to: TypeInputPeer, user_client: TelegramClient = None):
    """
    Forward messages in small pieces.

    Parameters
    ----------
    bot_client
    src_ch
    msg_list
    peer_to_forward_to
    user_client
    filtering_details

    Returns
    -------

    """
    grouped_msg_list = []  # https://github.com/LonamiWebs/Telethon/issues/1216
    non_grouped_msg_list = []
    last_grouped_id = -1

    for msg in reversed(msg_list):  # starting from the chronologically first
        # client.send_message(peer_to_forward_to, msg)
        # TODO: should be filtered during the filtering stage via rules?
        if asyncio.get_event_loop().run_until_complete(msg_is_action(msg=msg, client=bot_client, from_peer=src_ch,
                                                                     peer_to_forward_to=peer_to_forward_to)):
            continue
        if asyncio.get_event_loop().run_until_complete(msg_is_invoice(msg=msg, client=bot_client, from_peer=src_ch,
                                                                      peer_to_forward_to=peer_to_forward_to)):
            continue

        if msg.grouped_id is not None:  # the current message is a part of a group
            if msg.grouped_id == last_grouped_id:  # extending the same group
                grouped_msg_list.append(msg)
                logger.log(5, f"Group {msg.grouped_id} has one more message to be sent. Total size: {len(grouped_msg_list)}")
            else:  # a group is started after a non-group message(s)
                grouped_msg_list, non_grouped_msg_list = resolve_and_send_groups(bot_client=bot_client,
                                                                                 grouped_msg_list=grouped_msg_list,
                                                                                 non_grouped_msg_list=non_grouped_msg_list,
                                                                                 from_peer=src_ch.id,
                                                                                 peer_to_forward_to=peer_to_forward_to,
                                                                                 last_grouped_id=last_grouped_id,
                                                                                 user_client=user_client)
                last_grouped_id = msg.grouped_id
                grouped_msg_list.append(msg)
                logger.log(5, f"Group {msg.grouped_id} has one more message to be sent. "
                              f"Total size: {len(grouped_msg_list)}")
        else:  # the current message is a single message
            grouped_msg_list = send_group_if_non_empty(msg_list=grouped_msg_list, bot_client=bot_client,
                                                       from_peer=src_ch.id,
                                                       peer_to_forward_to=peer_to_forward_to,
                                                       last_grouped_id=last_grouped_id,
                                                       user_client=user_client)
            non_grouped_msg_list.append(msg)
            logger.log(5, f"Non-grouped messages list is extended. Total size: {len(non_grouped_msg_list)}")

    _, _ = resolve_and_send_groups(bot_client=bot_client,
                                   grouped_msg_list=grouped_msg_list,
                                   non_grouped_msg_list=non_grouped_msg_list,
                                   from_peer=src_ch.id,
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


async def msg_is_action(msg, client, from_peer, peer_to_forward_to):
    try:
        async with client:
            # TODO: check if regular messages have action. Looks like not
            if isinstance(msg.action, (MessageActionGroupCall, MessageActionGroupCall)):
                if msg.action.duration is None:
                    logger.info(f"{from_peer!r} started a call")
                    await client.send_message(peer_to_forward_to, f"{from_peer} started a call")
                else:
                    logger.info(f"{from_peer} ended a call")
                    await client.send_message(peer_to_forward_to, f"{from_peer} ended a call")
                return True
            if isinstance(msg.action, MessageActionPinMessage):
                logger.info(f"{from_peer!r} pinned a message")
                await client.send_message(peer_to_forward_to, f"{from_peer} pinned a message")
                return True
            if isinstance(msg.action, MessageActionGroupCallScheduled):
                logger.info(f"{from_peer!r} scheduled a group call")
                await client.send_message(peer_to_forward_to, f"{from_peer} scheduled a group call at {msg.action.schedule_date} UTC")
                return True
            return False
    except ChatWriteForbiddenError:
        logger.error(f"{await client.get_me()} can't forward from {from_peer!r} to {peer_to_forward_to} "
                     f"(caused by ForwardMessagesRequest)")  # add the owner as well


async def msg_is_invoice(msg, client, from_peer, peer_to_forward_to):
    try:
        async with client:
            if isinstance(msg.invoice, MessageMediaInvoice):
                logger.info(f"{from_peer!r} posten an invoice")
                await client.send_message(peer_to_forward_to, f"{from_peer} requests money with the following title: "
                                                              f"{msg.invoice.title}")
                return True
            return False
    except ChatWriteForbiddenError:
        logger.error(f"{await client.get_me()} can't forward from {from_peer!r} to {peer_to_forward_to} "
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
    with client:
        client(ForwardMessagesRequest(
            from_peer=peer,  # who sent these messages?
            id=msg_ids_to_forward,  # which are the messages? = grouped_ids
            to_peer=peer_to_forward_to,  # who are we forwarding them to?
            with_my_score=True
        ))
    logger.log(5, f'forwarded msg ids: {msg_ids_to_forward} to {peer_to_forward_to}')


# TODO: simplify function
def main(user_client: TelegramClient, bot_client: TelegramClient, recommender):
    last_channel_ids = get_last_channel_ids()
    feeds = get_feeds()  # which dst channel reads what source channels
    src2dst = invert_feeds(feeds, user_client)

    logger.log(7, f"Starting main with {len(src2dst)} source and {len(feeds)} destination channels")
    for src_ch, dst_ch_list in src2dst.items():  # pool of all channels for all users
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

            msg_list = check_new_channel_messages(src_ch=src_ch, last_channel_ids=last_channel_ids, client=user_client)
            if msg_list is not None:
                # time.sleep(randint(5, 10))
                # logger.debug(f"Found {len(msg_list)} message(s) in '{messages.chats[0].title}' ({src_ch.link})")
                logger.debug(f"Found {len(msg_list)} message(s) in '{src_ch!r})")

                # TODO: Here recommender system should act and decide to which users send the content
                for dst_ch in dst_ch_list:
                    # if dst_ch.id not in [-1001504355267, -1001851389727]:  # my channels
                    #     continue
                    user_id = get_channel_owner(dst_ch.id)
                    messages_checked_list, filtering_details = select_messages_for_dst_channel(msg_list=msg_list,
                                                                                               src_ch=src_ch,
                                                                                               dst_ch=dst_ch,
                                                                                               recommender=recommender,
                                                                                               user_client=user_client,
                                                                                               user_id=user_id)
                    with user_client:  # TODO: swich to async with?
                        # TODO: add logs after sending about sending time, original and changed message text
                        asyncio.get_event_loop().run_until_complete(log_messages(
                            client=user_client,
                            msg_list_before=msg_list,
                            filtering_details=filtering_details,
                            src_channel_id=src_ch.id,
                            src_channel_link=src_ch.link,
                            src_channel_name=src_ch.name,
                            user_channel_id=dst_ch.id,
                            user_channel_link=dst_ch.link,
                            user_channel_name=dst_ch.name,
                            user_id=user_id))

                    # TODO: replace peers to channels to improve visibility
                    # TODO: pass filtering details which will be renamed to action_details
                    group_and_forward_msgs(bot_client=bot_client, src_ch=src_ch, msg_list=messages_checked_list,
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
                                    recommender, user_client: TelegramClient, user_id) -> List[Message]:
    try:
        filtering_details = {k.id: None for k in msg_list}  # may be removed as initialized if empty inside the function
        # TODO: perform history check later wrt the dst channel and it's rb list
        with user_client:
            # logger.error('FILTERING IS NOT PERFORMED')
            filter_component = Filter(rule_base_check=True, history_check=True, client=user_client,
                                      dst_ch=dst_ch, use_common_rules=True,
                                      postfix_template_to_ignore=MSG_POSTFIX_TEMPLATE)
            messages_checked_list, filtering_details = filter_component.filter_messages(msg_list, filtering_details)

            if messages_checked_list:
                messages_checked_list, filtering_details = recommender.filter_messages(msg_list=messages_checked_list,
                                                                                       filtering_details=filtering_details,
                                                                                       user_client=user_client,
                                                                                       user_channel_id=dst_ch.id,
                                                                                       user_id=user_id,
                                                                                       threshold=0.47)
    except:
        logger.error('Failed to perform message selection. Passing further as they are', exc_info=True)
        messages_checked_list = msg_list
    return messages_checked_list, filtering_details


def check_new_channel_messages(src_ch: Channel, last_channel_ids, client):
    try:
        with client:
            # solution based on the last index mentioned in the json. We can't just check if there are some unread
            # messages because for that you have to be subscribed to the channel. Otherwise, you must anchor yourself to
            # some message ID in the past - this is what we do. For the just added channel with the default last
            # message id of 0, the batch will be large. But after disconnections this limit of 100 may be insufficient
            # and there will be gaps
            # peer=InputPeerChannel(entity_id, entity_hash)
            messages = None
            messages = asyncio.get_event_loop().run_until_complete(
                get_history(client=client, channel=src_ch, min_id=last_channel_ids[src_ch.id], limit=15))
            if len(messages) == 0:
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
                        unread_mark_read_n_messages = 4
                        messages = asyncio.get_event_loop().run_until_complete(get_history(client=client, channel=src_ch,
                                                                                           min_id=dialog.top_message - unread_mark_read_n_messages,
                                                                                           limit=unread_mark_read_n_messages))
                    else:  # this should not be triggered and has to be removed
                        logger.info(f"Channel {src_ch} has {dialog.unread_count} unread posts")
                        messages = asyncio.get_event_loop().run_until_complete(
                            get_history(client=client, channel=src_ch, min_id=dialog.read_inbox_max_id,
                                        limit=dialog.unread_count))
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

    if len(messages) == 0:
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
