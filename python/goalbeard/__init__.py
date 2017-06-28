import telepot
import telepot.aio
from telepot import glance
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

from skybeard.beards import BeardChatHandler, ThatsNotMineException, BeardDBTable
from skybeard.decorators import onerror, getargsorask, getargs
from skybeard.utils import get_args

from .utils import create_personal_listener_from_msg

from natural_time import natural_time
import string
import random


class GoalBeard(BeardChatHandler):

    __commands__ = [
        ('newgoal', 'new_goal', 'Used to set a new goal.'),
        ('mygoals', 'show_goals', 'Shows all goals you currently have.'),
        ('setreminder', 'set_reminder',
         'Sets times at which you will be reminded of your goals.'),
        ('showreminders', 'show_reminders',
         'Show all reminders you have set.')
    ]

    __userhelp__ = ('Used to set goals and help achieve them. As '
                    'goals can often be private they will only ever'
                    'be posted to private chats with the user').strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Table for storign goals
        self.goal_table = BeardDBTable(self, 'goals')
        self.reminders_table = BeardDBTable(self, 'reminders')
        with self.reminders_table as table:
            table.delete(rid='MTES')
            table.delete(rid='nuJy')
        # Reload reminders as events
        self._reload_reminders()
        self.router.routing_table['_show_goals'] = self.on_show_goals
        self.reminders = []

    async def new_goal(self, msg):
        '''Add a new goal for the user'''
        print(msg)
        my_listener = await create_personal_listener_from_msg(self, msg)
        u_id = msg['from']['id']
        args = get_args(msg)
        if args:
            # Get the goal the user input
            goal = ' '.join(args)
        else:
            # Ask the user what their goal is
            await self.sender.sendMessage("What is your goal?")
            reply = await my_listener.wait()
            goal = reply['text']
        await self.sender.sendMessage("How long do you want this goal for?")
        time_msg = await my_listener.wait()
        date_time = natural_time(time_msg['text'])
        # Save the goal to the table
        with self.goal_table as table:
            r_id = "".join(
                    [random.choice(string.ascii_letters) for x in range(4)])
            table.insert(dict(
                    uid = u_id,
                    item = goal,
                    until = date_time,
                    rid = r_id))
            await self.sender.sendMessage(
                    "'{}' added to goals until {}".format(goal, date_time))

    async def _make_keyboard(self, items, kb_name):
        inline_keyboard = []
        for item in items:
            inline_keyboard.append([
                    InlineKeyboardButton(
                        text=item['item'],
                        callback_data=self.serialize(
                                {'rid':item['rid'],'name':kb_name}))])
        markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        return markup

    async def _get_user_goals(self, u_id):
        '''Gets all goals set by a user'''
        with self.goal_table as table:
            matches = table.find(uid=u_id)
        items = [match for match in matches]
        return items

    async def show_goals(self, msg):
        '''
        Shows all the users current goals.

        Clicking a goal will give the option to delete it.
        '''
        u_id = msg['from']['id']
        items = await self._get_user_goals(u_id)
        if not items:
            await self.sender.sendMessage("You have no goals at the moment")
            return
        keyboard = await self._make_keyboard(items, 'goal_kb')
        await self.bot.sendMessage(
                chat_id=u_id,
                text='Your current goals. Click on a goal to remove it.',
                reply_markup=keyboard)

    async def on_callback_query(self, msg):
        query_id, from_id, query_data = glance(msg, flavor='callback_query')
        match = None
        try:
            # Get current text in the message
            data = self.deserialize(query_data)
            r_id = data['rid']
            name = data['name']
            if name == 'goal_kb':
                with self.goal_table as table:
                    match = table.find_one(rid=r_id)
                    if not match:
                        # Ignore where entry is already deleted
                        print("Entry already deleted")
                        return
                    if match['uid'] != from_id:
                        # Ignore where another user tries to delete an entry
                        # Thogh this shouldn't be possible...
                        print("User tried to delete an entry that was not their's")
                        return
                    # Delete the item
                    table.delete(rid=r_id)
                # Update the list of goals
                items = await self._get_user_goals(from_id)
                if items:
                    keyboard = await self._make_keyboard(items, 'goal_kb')
                    await self.bot.editMessageText(
                            telepot.origin_identifier(msg),
                            text='Your current goals. Click on a goal to remove it',
                            reply_markup=keyboard)
                else:
                    await self.bot.editMessageText(
                            telepot.origin_identifier(msg),
                            text='You have no goals at the moment.')
            elif name == 'rmd_kb':
                with self.reminders_table as table:
                    match = table.find_one(rid=r_id)
                    if not match:
                        # Ignore where entry is already deleted
                        print("Entry already deleted")
                        return
                    if match['uid'] != from_id:
                        # Ignore where another user tries to delete an entry
                        # Thogh this shouldn't be possible...
                        print("User tried to delete an entry that was not their's")
                        return
                    # Delete the item
                    table.delete(rid=r_id)
                # Update the list of goals
                items = await self._get_user_reminders(from_id)
                if items:
                    keyboard = await self._make_keyboard(items, 'rmd_kb')
                    await self.bot.editMessageText(
                            telepot.origin_identifier(msg),
                            text='Your current reminders. Click on a reminder to remove it.',
                            reply_markup=keyboard)
                else:
                    await self.bot.editMessageText(
                            telepot.origin_identifier(msg),
                            text='You have no reminders at the moment.')

        except ThatsNotMineException:
            pass

    async def set_reminder(self, msg):
        '''Sets reminders for specific times throughout the day'''
        u_id = msg['from']['id']
        my_listener = await create_personal_listener_from_msg(self, msg)
        await self.sender.sendMessage(
                "What time would you like to schedule a reminder for?")
        reply = await my_listener.wait()
        time = natural_time(reply['text']).timestamp()
        # Create the event and append it to reminders (easier to cancel)
        self.reminders.append(
                self.scheduler.event_at(time, ('_show_goals',
                                               {'id':u_id, 'time':time})))
        # Add it to the table
        with self.reminders_table as table:
            r_id = "".join(
                    [random.choice(string.ascii_letters) for x in range(4)])
            table.insert(dict(
                    uid = u_id,
                    item = reply['text'],
                    time = time,
                    rid = r_id))
        await self.sender.sendMessage("Reminder set for {}".format(time))

    async def on_show_goals(self, data):
        u_id = data['_show_goals']['id']
        await self.show_goals({'from':{'id':u_id}})
        # Create new event so it is a perpetual reminder
        time = data['_show_goals']['time']
        # Update the database entry
        with self.reminders_table as table:
            matches = table.find(time=time)
            print(matches)
            items = [match for match in matches]
            item = items[0]
            table.delete(time=time)
            # Increment the time by a day
            time = time + 86400
            item['time'] = time
            table.insert(item)
        # Add new event to the scheduler
        self.scheduler.event_at(time, ('_show_goals',
                                       {'id':u_id, 'time':time}))

    def _reload_reminders(self):
        with self.reminders_table as table:
            matches = table.all()
        items = [match for match in matches]
        for item in items:
            # Create the events
            self.scheduler.event_at(item['time'],
                ('_show_goals', {'id':item['uid'], 'time':item['time']}))

    async def _get_user_reminders(self, u_id):
        with self.reminders_table as table:
            matches = table.find(uid=u_id)
            items = [match for match in matches]
        return items

    async def show_reminders(self, msg):
        u_id = msg['from']['id']
        items = await self._get_user_reminders(u_id)
        if not items:
            await self.sender.sendMessage("You have no reminders at the moment")
            return
        keyboard = await self._make_keyboard(items, 'rmd_kb')
        await self.bot.sendMessage(
                chat_id=u_id,
                text='Your current reminders. Click on a reminder to remove it.',
                reply_markup=keyboard)
