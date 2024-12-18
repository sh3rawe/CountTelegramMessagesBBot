from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime, timedelta
import pytz
import logging
import os
import json
from collections import defaultdict

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MessageCounterBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.data_dir = "bot_data"
        self.ensure_data_directory()
        
        # Load saved data
        self.message_history = self.load_messages()
        self.admin_users = self.load_data('admin_users.json', set())
        self.group_names = self.load_data('group_names.json', {})
        
        # Convert set from loaded JSON
        self.admin_users = set(self.admin_users)
        
        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("authorize", self.authorize))
        self.application.add_handler(CommandHandler("listgroups", self.list_groups))
        self.application.add_handler(CommandHandler("count", self.count_messages))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.track_message))
        self.application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_chat_members))
        self.application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, self.handle_left_chat))
        
        # Error handler
        self.application.add_error_handler(self.error_callback)

    def ensure_data_directory(self):
        """Create data directory if it doesn't exist."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_messages(self):
        """Load message history from JSON file with proper defaultdict handling."""
        file_path = os.path.join(self.data_dir, 'message_history.json')
        message_history = defaultdict(list)
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for group_id, messages in data.items():
                        message_history[group_id] = messages
        except Exception as e:
            logger.error(f"Error loading message history: {e}")
        
        return message_history

    def load_data(self, filename, default_value):
        """Load data from JSON file."""
        file_path = os.path.join(self.data_dir, filename)
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
        return default_value

    def save_messages(self):
        """Save message history to JSON file."""
        file_path = os.path.join(self.data_dir, 'message_history.json')
        try:
            message_dict = dict(self.message_history)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(message_dict, f, ensure_ascii=False, indent=2)
            logger.info("Messages saved successfully")
        except Exception as e:
            logger.error(f"Error saving message history: {e}")

    def save_data(self, filename, data):
        """Save data to JSON file."""
        file_path = os.path.join(self.data_dir, filename)
        try:
            if isinstance(data, set):
                data = list(data)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")

    async def handle_new_chat_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle when bot is added to a new group."""
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                group_id = str(update.message.chat_id)
                self.group_names[group_id] = update.message.chat.title
                self.save_data('group_names.json', self.group_names)
                logger.info(f"Bot added to group: {update.message.chat.title} (ID: {group_id})")
                await update.message.reply_text("Thanks for adding me! I'll start tracking messages now.")

    async def handle_left_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle when bot is removed from a group."""
        if update.message.left_chat_member.id == context.bot.id:
            group_id = str(update.message.chat_id)
            if group_id in self.group_names:
                del self.group_names[group_id]
                if group_id in self.message_history:
                    del self.message_history[group_id]
                self.save_data('group_names.json', self.group_names)
                self.save_messages()
                logger.info(f"Bot removed from group: {update.message.chat.title} (ID: {group_id})")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        if update.message.chat.type == 'private':
            await update.message.reply_text(
                'Welcome to ICPC Zagazig University Message Counter Bot!\n\n'
                'Available commands:\n'
                '/authorize - Register yourself as an admin\n'
                '/listgroups - Show all groups the bot is in\n'
                '/count <group_id> <username> <start_date> <end_date> - Count messages\n\n'
                'Date format: YYYY-MM-DD'
            )
        else:
            group_id = str(update.message.chat_id)
            self.group_names[group_id] = update.message.chat.title
            self.save_data('group_names.json', self.group_names)
            await update.message.reply_text('Bot is ready to track messages in this group.')

    async def authorize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Authorize a user to use the bot."""
        if update.message.chat.type == 'private':
            user_id = update.message.from_user.id
            self.admin_users.add(user_id)
            self.save_data('admin_users.json', self.admin_users)
            await update.message.reply_text('You are now authorized to use the bot.')

    async def list_groups(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all groups the bot is in."""
        if update.message.chat.type != 'private' or update.message.from_user.id not in self.admin_users:
            await update.message.reply_text('You need to be authorized to use this command. Use /authorize first.')
            return

        if not self.group_names:
            await update.message.reply_text('I am not added to any groups yet. Please add me to a group first.')
            return

        groups_list = '\n'.join([f"Group: {name}\nID: {id_}\n" for id_, name in self.group_names.items()])
        await update.message.reply_text(
            'Groups I am tracking:\n\n'
            f'{groups_list}\n'
            'Use these IDs with the /count command.'
        )

    async def track_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track each message in the group."""
        if update.message.chat.type in ['group', 'supergroup']:
            message_data = {
                'user_id': update.message.from_user.id,
                'username': update.message.from_user.username,
                'timestamp': update.message.date.timestamp(),
                'text': update.message.text
            }
            group_id = str(update.message.chat_id)
            self.message_history[group_id].append(message_data)
            self.group_names[group_id] = update.message.chat.title
            
            # Save messages immediately
            self.save_messages()
            self.save_data('group_names.json', self.group_names)

    async def count_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Count messages for a specific user within a date range."""
        if update.message.chat.type != 'private' or update.message.from_user.id not in self.admin_users:
            await update.message.reply_text('You need to be authorized to use this command. Use /authorize first.')
            return

        try:
            if len(context.args) != 4:
                await update.message.reply_text(
                    'Usage: /count group_id username YYYY-MM-DD YYYY-MM-DD\n'
                    'Use /listgroups to see available group IDs'
                )
                return

            group_id = str(int(context.args[0]))
            username = context.args[1].replace('@', '')
            start_date = datetime.strptime(context.args[2], '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            end_date = datetime.strptime(context.args[3], '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            end_date = end_date + timedelta(days=1)  # Include the entire end date

            if group_id not in self.group_names:
                await update.message.reply_text('Error: Bot is not in this group or group ID is invalid.')
                return
            
            # Count messages
            message_count = 0
            start_timestamp = start_date.timestamp()
            end_timestamp = end_date.timestamp()
            
            for msg in self.message_history[group_id]:
                msg_timestamp = float(msg['timestamp'])
                if (msg['username'] == username and 
                    start_timestamp <= msg_timestamp <= end_timestamp):
                    message_count += 1

            group_name = self.group_names.get(group_id, 'Unknown Group')
            response = (f"In group '{group_name}':\n"
                       f"User @{username} sent {message_count} messages "
                       f"between {context.args[2]} and {context.args[3]}")
            await update.message.reply_text(response)

        except (IndexError, ValueError) as e:
            await update.message.reply_text(
                'Error: Please check the format of your command.\n'
                'Usage: /count group_id username YYYY-MM-DD YYYY-MM-DD\n'
                'Use /listgroups to see available group IDs'
            )
            logger.error(f"Error in count_messages: {str(e)}")

    async def error_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log Errors caused by Updates."""
        logger.warning(f'Update "{update}" caused error "{context.error}"')

    def run(self):
        """Start the bot."""
        self.application.run_polling()
        logger.info("Bot started")

if __name__ == '__main__':
    # Replace 'YOUR_BOT_TOKEN' with your actual bot token
    bot = MessageCounterBot('8073961508:AAFiSBbU0rYh5VlSpxfvH7SutmsNHfvhmnQ')
    bot.run()