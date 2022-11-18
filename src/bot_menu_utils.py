from telethon import events, types, Button

from math import ceil
from src import config, bot_client
import re
from database_utils import get_users
from utils import get_channel_link

# command: [button_name, help_descr]
COMMANDS = {  # command description used in the "help" command
    '/start': ["start", "Registers the users and sends the greetings message"],

    '/help': ["textual help (CLI commands)",
              'Gives you information about the available commands in text.'
              "\nYour feedback is appreciated.\nPlease, contact t.me/OlegBEZb regarding any issues"],

    '/about': ["about", "Sends the detailed description of the project and its usage"],

    '/my_channels': ["show my channels",
                     "This command shows all your channels which fetch updates from this bot"],

    '/channel_info': ["show channel info",
                      ("This command shows source channels for one of your channels. This command requires 1 argument "
                       "from you: link to your channel."
                       "\nExample: /channel_info t.me/your_destination_channel")],

    '/add_to_channel': ["add source channel to my channel",
                        ("This command adds a new source channel which content will be redirected to your channel."
                         " This command requires 2 arguments from you: what channel to add and where to add. These two"
                         " arguments are both links to telegram channels."
                         "\nExample: /add_to_channel t.me/channel_of_interest t.me/your_destination_channel")],
}


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


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


@bot_client.on(events.NewMessage(pattern='/hlep'))
async def command_help_test(event):
    sender_id = event.chat_id
    if not event.is_private:  # replace with event.is_group\channel\private
        await event.reply(
            "Contact me in PM to get the help menu",
            buttons=[[Button.url("Click me for help!", config.bot_url)]],
        )
        return

    # some commands may be called right from here. for others another sub call to get arguments is needed
    # may be addressed by level of depth
    cmd_text2data = {btn_name: cmd for cmd, (btn_name, _) in COMMANDS.items()}
    cmd_text2data["add source channel to my channel"] = 'button_' + cmd_text2data["add source channel to my channel"]
    cmd_text2data['show channel info'] = 'button_' + cmd_text2data['show channel info']

    buttons = paginate_help(event, 0, cmd_text2data, "helpme")
    await event.reply("Select one of the following", buttons=buttons)
    # await bot_client.send_message(sender_id, "Select one of the following", buttons=buttons)


# TODO: show channel links to the user. Pass these links to the /channel_info func as an argument
@bot_client.on(events.CallbackQuery(data=b"button_/channel_info"))
async def button_channel_info(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    users = get_users()
    user_channels = users[str(sender_id)]
    if not user_channels:
        await event.reply("You haven't added the bot to any of your channels yet")
        return
    user_channels_links = [await get_channel_link(bot_client, ch) for ch in user_channels]
    cmd_text2data = {str(ch): f"/channel_info {ch}" for ch in user_channels_links}
    buttons = paginate_help(event, 0, cmd_text2data, "channel",
                            shape=(len(user_channels), 1)
                            )
    await event.reply("Select one of the following", buttons=buttons)
