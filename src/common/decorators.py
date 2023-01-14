import functools
from telethon import Button
from src import config


def check_direct(func):
    @functools.wraps(func)
    async def wrapper_decorator(event):
        if not event.is_private:  # isinstance(event.chat, types.User)  # replace with event.is_group\channel\private
            await event.reply(
                "Communication with the bot has to be performed only in direct messages, not public channels",
                buttons=[[Button.url("Click here to start!", config.bot_url)]])
            return
        value = await func(event)
        return value
    return wrapper_decorator


def check_admin(func):
    @functools.wraps(func)
    async def wrapper_decorator(event):
        sender_id = event.chat_id
        if int(sender_id) != config.my_id:
            await event.reply("You are not allowed to perform this action")
            return
        value = await func(event)
        return value

    return wrapper_decorator


def sending_confirmation(func):
    pass


def check_ownership(func):
    # users = get_users()
    # if dst_ch.id not in users[sender_id]:
    #     await event.reply("You are not allowed to perform this action")
    #     return
    pass


def show_menu_before_return(func):
    pass
