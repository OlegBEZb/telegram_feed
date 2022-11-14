from telethon import TelegramClient, events, types
import telethon.utils as tutils

import config

import logging

from src.utils import get_user_display_name

logging.basicConfig(
    # filename="MainClient.log",
    format='%(asctime)s %(module)s %(levelname)s: %(message)s',
    level=logging.INFO,
    # level=log_level,
    # datefmt='%Y-%m-%d %I:%M:%S',
    force=True)
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logging.getLogger('telethon').setLevel(logging.WARNING)


from utils import check_channel_correctness, get_users, save_users, get_feeds, \
    save_feeds, update_user, update_feed, list_to_str_newline, get_channel_link

COMMANDS = {  # command description used in the "help" command
    'start'         : ("Welcome to the 'telefeed' project. You have to add this bot as an administrator to your "
                       "**public** channel. If you don't have any, create one. For each created channel you will be able "
                       "to get personalised feed.\n**Note**: your private information is not visible in any way for "
                       "other users but still visible for the bot creator for debugging purposes. In future, this "
                       "personal information will be private for everyone including admins and developers"),

    'help'          : ('Gives you information about the available commands.'
             "\nYour feedback is appreciated.\nPlease, contact t.me/OlegBEZb regarding any issues"),

    'about'         : ("The purpose of this bot is to aggregate all your channels into one feed, as well as filter ads "
                       "and duplicated content."
                       "For better recommendations, you can allow reactions on your public channel and use them for the "
                       "content published. The most important reactions for us are '👍' and '👎'. For spam use '💩' and '🤬'."
                       "\n**Note**: your private information is not visible in any way for "
                       "other users but still visible for the bot creator for debugging purposes. In future, this "
                       "personal information will be private for everyone including admins and developers"),

    'my_channels'   : ("This command shows all you channels which fetch updates from this bot"),

    'channel_info'  : ("This command shows source channels for one of your channels. This command requires 1 argument "
                       "from you: link to your channel."
                       "\nExample: /channel_info t.me/your_destination_channel"),

    'add_to_channel': ("This command adds a new source channel which content will be redirected to your channel."
                       " This command requires 2 arguments from you: what channel to add and where to add. These two"
                       " arguments are both links to telegram channels."
                       "\nExample: /add_to_channel t.me/channel_of_interest t.me/your_destination_channel"),
}

# TODO: move to a separate file and dynamically add to the list of handlers like in
# https://github.com/Lonami/TelethonianBotExt
# these commands should be available and visible only for devs
ADMIN_COMMANDS = {
    'users': 'Lists users'
}

bot = TelegramClient('bot', config.api_id, config.api_hash).start(bot_token=config.bot_token)


# ChatAction only handles MessageService in this case, what's the chat type you're adding to. removal should be decided by Telegram.
# You can use Raw and handle UpdateChannel*
# A broadcast channel doesn't have action messages opposite of groups. and Telegram api is very changing, ChatAction
# needs to support those new changes at some point. since remove actions aren't sent.

# @client.on(events.Raw(telethon.types.UpdateBotChatInviteRequester))
# async def approve(e):
#     await client(functions.messages.HideChatJoinRequestRequest(e.peer, e.user_id, approved=True or False
#       )
# )


# needed to catch all kinds of events related to bots because for some reason these events are
# not covered well with standard methods
# @bot.on(events.Raw)
# async def handler(update):
#     # Print all incoming updates
#     print(update.stringify())


@bot.on(events.Raw(types.UpdateChannelParticipant))
# ChannelParticipant, ChannelParticipantSelf, ChannelParticipantCreator, ChannelParticipantAdmin, ChannelParticipantBanned, ChannelParticipantLeft
async def update_channel_participant(e):
    channel_id = int('-100' + str(e.channel_id))
    if e.new_participant:
        # TODO: decide with chat_id types: int or str
        if isinstance(e.new_participant, types.ChannelParticipantAdmin) and e.new_participant.user_id == config.bot_id:
            logger.info(f"Bot is added as admin at '{channel_id}' due to '{e.actor_id}'s action")

            users = get_users()
            users = update_user(users, e.actor_id, channel_id, add_not_remove=True)
            save_users(users)

    elif e.prev_participant:
        if isinstance(e.prev_participant, types.ChannelParticipantAdmin) and e.prev_participant.user_id == config.bot_id:
            logger.info(f"Bot is no longer an admin at '{channel_id}' due to '{e.actor_id}'s action")

            users = get_users()
            users = update_user(users, e.actor_id, channel_id, add_not_remove=False)
            save_users(users)
            # TODO: remove related records from the DB (feeds, etc.)


@bot.on(events.NewMessage(pattern='/help'))
async def command_help(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    help_text = "The following commands are available: \n"
    for key in COMMANDS:  # generate help text out of the commands dictionary defined at the top
        help_text += "/" + key + ": "
        help_text += COMMANDS[key] + "\n"
    await bot.send_message(sender_id, help_text)
    logger.debug(f"Sent help to {sender_id}")


@bot.on(events.NewMessage(pattern='/start'))
async def command_start(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    await bot.send_message(sender_id, COMMANDS['start'])
    users = get_users()
    if str(sender_id) not in users:  # if user hasn't used the "/start" command yet:
        users[sender_id] = []
        save_users(users)
        await command_help(event)  # show the new user the help page
        logger.info(f"New user {sender_id} started the bot")
    else:
        await bot.send_message(sender_id, "I already have you in my database")


@bot.on(events.NewMessage(pattern='/about'))
async def command_about(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    await bot.send_message(sender_id, COMMANDS['about'])
    logger.debug(f"Sent about to {sender_id}")


@bot.on(events.NewMessage(pattern='/channel_info'))
async def command_channel_info(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    message = event.message
    _, dst_ch = message.text.split()
    dst_ch = check_channel_correctness(dst_ch)

    entity = await bot.get_input_entity(dst_ch)
    dst_ch_id = tutils.get_peer_id(entity)
    # dst_ch_id = get_channel_id(bot, dst_ch)

    users = get_users()
    if dst_ch_id not in users[str(sender_id)]:
        await event.reply(f"You are not allowed to perform this action")
        return

    feeds = get_feeds()
    reading_list = feeds[dst_ch]
    if not reading_list:
        await event.reply(f"Your reading list is empty")
    else:
        await event.reply(f"Your reading list of {len(reading_list)} item(s) (sorted chronologically):\n{list_to_str_newline(reading_list)}")


@bot.on(events.NewMessage(pattern='/my_channels'))
async def command_my_channels(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    users = get_users()
    users_channels = users[str(sender_id)]
    if len(users_channels) == 0:
        await event.reply(f"You haven't added the bot to any of your channels yet")
    else:
        users_channels_links = [await get_channel_link(bot, ch) for ch in users_channels]
        await event.reply(f"Your channels (sorted chronologically):\n{list_to_str_newline(users_channels_links)}")


@bot.on(events.NewMessage(pattern='/add_to_channel'))
async def command_add_to_channel(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    try:
        message = event.message
        # TODO: add any number of channels before the last/destination one
        _, src_ch, dst_ch = message.text.split()
        # TODO: add assert for the incorrect format
        src_ch, dst_ch = check_channel_correctness(src_ch), check_channel_correctness(dst_ch)

        entity = await bot.get_input_entity(dst_ch)
        dst_ch_id = tutils.get_peer_id(entity)
        # dst_ch_id = get_channel_id(bot, dst_ch)

        users = get_users()
        if dst_ch_id not in users[str(sender_id)]:
            await event.reply(f"You are not allowed to perform this action. Try to add the bot to your channel as admin.")
            return

        feeds = get_feeds()

        if src_ch in feeds:
            # TODO: think about potential solution
            await event.reply(f"You can not add somebody's target channel as your source because of potential infinite loops")
            return

        update_feed(feeds, dst_ch, src_ch, add_not_remove=True)
        save_feeds(feeds)
        # TODO: add notification that the channel was already there
        await event.reply(f"Added! Now your reading list is the following:\n{list_to_str_newline(feeds[dst_ch])}")
    except:
        await event.reply(f"Was not able to add channel. Check if your destination channel is public and the bot is added as admin")
        logger.error(f"User {sender_id} failed to add channel {src_ch} to {dst_ch}", exc_info=True)
        return

@bot.on(events.NewMessage(pattern='/users'))
async def admin_command_users(event):
    if not isinstance(event.chat, types.User):
        return
    sender_id = event.chat_id
    if int(sender_id) != config.my_id:
        await event.reply(f"You are not allowed to perform this action")
        return
    users = get_users()
    if len(users) == 0:
        await event.reply(f"You don't have any yet")
    else:
        # TODO: add the number of channels per user
        user_names = [await get_user_display_name(bot, int(u)) for u in users]
        await event.reply(f"Your {len(users)} user(s) (sorted chronologically):\n{list_to_str_newline(user_names)}")


@bot.on(events.NewMessage)  # UpdateNewMessage
async def echo_all(event):
    if not isinstance(event.chat, types.User):
        return
    message = event.message
    cmd = message.text.split()[0]
    if cmd[0] == '/':
        cmd = cmd[1:]
    if cmd not in COMMANDS:
        await event.reply(f"This is an unrecognized command. Use /help to list all available commands")


bot.run_until_disconnected()
