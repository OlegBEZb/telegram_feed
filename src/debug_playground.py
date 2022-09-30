from typing import List
import time
import pandas as pd
import config

from telethon.sync import TelegramClient
from telethon.tl.types import MessageFwdHeader, PeerChannel, MessageEntityTextUrl
from telethon.tl.patched import Message
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.messages import GetPeerDialogsRequest, MarkDialogUnreadRequest
from telethon.tl.functions.messages import ForwardMessagesRequest, GetHistoryRequest
from telethon.tl.functions.channels import GetFullChannelRequest

from utils import OpenUpdateTime, SaveUpdateTime, SaveNewTime
from utils import check_copypaste, check_msg_list_for_adds, check_channel_correctness

good_reactions = ['👍', '❤', '🔥', '❤\u200d🔥', '🎉']
bad_reactions = ['👎', '👏', '😁', '💩', '🤮']


def get_reactions(msg: Message):
    if msg.reactions is not None:
        reactions = msg.reactions.results
        d = {}
        for reaction in reactions:
            d[reaction.reaction] = reaction.count
        return d


if __name__ == '__main__':

    api_id = config.api_id
    api_hash = config.api_hash
    isNotConnected = True

    connection_attempts = 1
    while isNotConnected:
        try:
            print(f"Connection attempt: {connection_attempts}")
            client = TelegramClient('telefeed_client', api_id, api_hash)
            client.start()
            print('TelegramClient is started\n')
            isNotConnected = False
        except Exception as e:
            connection_attempts += 1
            print(str(e))
            time.sleep(30)

    # Debugging stuff
    # from telethon.tl.types import PeerChannel
    # print('client.get_input_entity(PeerChannel(1051500113))', client.get_input_entity(PeerChannel(1051500113)))

    my_channel_history = client(GetHistoryRequest(
        peer=config.MyChannel,
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=100,
        max_id=0,
        min_id=0,
        hash=0
    ))
    target_keys = ['date', 'raw_text', 'message', 'pinned']
    save_list = []
    for msg in my_channel_history.messages:
        reactions_dict = get_reactions(msg)
        if reactions_dict is not None:
            # sentiment = 0
            # for r in good_reactions:
            #     sentiment += reactions_dict.get(r, 0)
            # for r in bad_reactions:
            #     sentiment -= reactions_dict.get(r, 0)
            # if sentiment < 0:
            #     print(msg.id, reactions_dict)
            d = {k: v for k, v in msg.__dict__.items() if k in target_keys}
            d.update(reactions_dict)
            if msg.entities is not None:
                d['entities_num'] = len(msg.entities)
                entity_urls = [ent.url for ent in msg.entities if isinstance(ent, MessageEntityTextUrl)]
                d['entity_urls'] = entity_urls if entity_urls else None
            save_list.append(d)
    pd.DataFrame(save_list).to_csv('data/my_channel_msgs_reactions.csv', index=False)

    # print([(reaction.reaction, reaction.count) for msg in my_channel_history.messages for reaction in msg.reactions.results], 'reactions')

    # print('len(my_channel_history.messages)', len(my_channel_history.messages))
    # print('my history ids', [msg.id for msg in my_channel_history.messages])
    # # print('my_dick', my_dick.__dict__)
    #
    # other_dick = client(functions.messages.GetHistoryRequest(
    #     peer='https://t.me/nn_for_science',
    #     offset_id=0,
    #     offset_date=0,
    #     add_offset=0,
    #     limit=1,
    #     max_id=0,
    #     min_id=0,
    #     hash=0
    # ))
    # print('other_dick', other_dick)

    # print('shared fields', {k: v for k, v in my_dick.items() if other_dick[k] == v})

    # messages = client(GetHistoryRequest(
    #     peer=config.MyChannel,
    #     offset_id=0,
    #     offset_date=0,
    #     add_offset=0,
    #     limit=10,
    #     max_id=0,
    #     min_id=0,
    #     hash=0
    # ))

    # print([get_reactions(msg) for msg in messages.messages], 'reactions')
    # print('messages.messages[0].__dict__', messages.messages[0].__dict__)

    # messages = client(GetHistoryRequest(
    #     peer='https://t.me/DeepStuffChannel',
    #     offset_id=0,
    #     offset_date=0,
    #     add_offset=0,
    #     limit=1,
    #     max_id=0,
    #     min_id=0,
    #     hash=0
    # ))
    # check_msg_list_for_adds(messages.messages)
    # print('messages.__dict__', messages.__dict__)
    # print('messages.messages', messages.messages)
    # print('messages.messages type', type(messages.messages))
    # print('messages.messages', [txt.message[:10] for txt in messages.messages])
    # print('messages.messages[0].__dict__', messages.messages[0].__dict__)
    # print('messages.messages[0].fwd_from', messages.messages[0].fwd_from)
    # print('messages.messages[0].fwd_from.from_id', messages.messages[0].fwd_from.from_id)
    # print('messages.chats[0].__dict__', messages.chats[0].__dict__)
    # print('messages.users[0].__dict__', messages.users[0].__dict__)
    # if messages.messages:  # nothing new from the last read
    #     print('messages.messages[0].__dict__', messages.messages[0].__dict__)
    #
    # result = client(GetPeerDialogsRequest(
    #         peers=['https://t.me/DeepFaker']
    #     ))
    # print('result.dialogs[0].__dict__', result.dialogs[0].__dict__)
    # print('result.dialogs[0].peer.__dict__', result.dialogs[0].peer.__dict__)
    # from telethon.utils import get_display_name
    # print('get_display_name(result.dialogs[0].peer)', get_display_name(result.dialogs[0].peer))
    # print("result.dialogs[0]['peer']", result.dialogs[0]['peer'])
