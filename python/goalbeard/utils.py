

async def create_personal_listener_from_msg(my_bot, msg):
    my_listener = my_bot.bot.create_listener()
    my_listener.capture([{'from': {'id': msg['from']['id']}},
                         {'chat': {'id': msg['chat']['id']}}])
    return my_listener
