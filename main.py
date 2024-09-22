import json
import random
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Router
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from a .env file for secure token and channel ID
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # Secure the bot token
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')  # Secure the channel ID

# Set up basic logging (info level for better debugging)
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=TOKEN, session=AiohttpSession())
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# File to persist already sent posts
PERSISTENCE_FILE = Path('already_sent.json')

# Helper function to load JSON data with UTF-8 encoding
def load_data(file_path):
    logging.info(f"Loading data from {file_path}")
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# Helper function to save the already sent posts to persistence
def save_sent_data():
    logging.info("Saving sent posts data")
    with open(PERSISTENCE_FILE, 'w', encoding='utf-8') as file:
        json.dump(already_sent_today, file)

# Load persisted sent posts data if available
if PERSISTENCE_FILE.exists():
    with open(PERSISTENCE_FILE, 'r', encoding='utf-8') as file:
        already_sent_today = json.load(file)
else:
    # Initialize if file doesn't exist
    already_sent_today = {
        "forex": [],
        "motivation": [],
        "morning": [],
        "weekend": []
    }

# Function to retry sending a post on failure
async def send_post(post, channel_id, retries=3, delay=5):
    try:
        logging.info(f"Sending post of type {post['type']} to channel {channel_id}")
        if post["type"] == "image":
            await bot.send_photo(chat_id=channel_id, photo=post["media"], caption=post.get("caption", ""))
        elif post["type"] == "video":
            await bot.send_video(chat_id=channel_id, video=post["media"], caption=post.get("caption", ""))
        elif post["type"] == "text":
            await bot.send_message(chat_id=channel_id, text=post["content"])
        logging.info(f"Post sent successfully")
    except Exception as e:
        if retries > 0:
            logging.error(f"Error sending post: {e}. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            await send_post(post, channel_id, retries - 1, delay * 2)  # Exponential backoff
        else:
            logging.error(f"Failed to send post after retries: {e}")

# Function to get random posts without repeating previously sent posts
def get_random_posts(file_path, num_posts=5, post_type="forex"):
    data = load_data(file_path)
    available_posts = [post for post in data if post not in already_sent_today[post_type]]
    
    # If fewer available posts than needed, reset the sent list and reshuffle
    if len(available_posts) < num_posts:
        logging.info(f"Not enough available {post_type} posts. Resetting sent posts list.")
        already_sent_today[post_type] = []
        available_posts = data

    # Select random posts
    selected_posts = random.sample(available_posts, min(num_posts, len(available_posts)))
    already_sent_today[post_type].extend(selected_posts)
    
    # Save the updated sent posts to persistence
    save_sent_data()
    
    return selected_posts

# Function to calculate time intervals between posts
def get_time_intervals(start_hour, end_hour, num_posts):
    total_minutes = (end_hour - start_hour) * 60
    interval_minutes = total_minutes // num_posts  # Calculate the gap between posts
    return [
        (datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0) + timedelta(minutes=i * interval_minutes)).strftime("%H:%M")
        for i in range(num_posts)
    ]

# Function to schedule posts at specific times
async def schedule_post(post_type, json_file, num_posts=5):
    logging.info(f"Scheduling {num_posts} {post_type} posts")
    posts = get_random_posts(json_file, num_posts, post_type)
    intervals = get_time_intervals(8, 20, num_posts)  # Post between 8 AM and 8 PM
    for idx, post in enumerate(posts):
        logging.info(f"Scheduling post {idx + 1}/{num_posts} with a 30 minute interval")
        await asyncio.sleep(idx * 1800)  # 30 minutes interval
        await send_post(post, CHANNEL_ID)

# Forex posts (5 random posts daily)
async def schedule_forex_posts():
    await schedule_post("forex", "forex_data.json", num_posts=5)

# Motivation posts (5 random posts daily)
async def schedule_motivation_posts():
    await schedule_post("motivation", "motivation_data.json", num_posts=5)

# Morning post (1 post daily at 7 AM)
async def morning_post():
    data = load_data('morning_data.json')
    post = random.choice([p for p in data if p not in already_sent_today["morning"]])
    already_sent_today["morning"] = [post]  # Ensure no repetition
    await send_post(post, CHANNEL_ID)
    save_sent_data()

# Weekend post (1 post every Friday at 7:45 PM)
async def weekend_post():
    data = load_data('weekend_data.json')
    post = random.choice([p for p in data if p not in already_sent_today["weekend"]])
    already_sent_today["weekend"] = [post]
    await send_post(post, CHANNEL_ID)
    save_sent_data()

# Schedule all types of posts
async def schedule_all_posts():
    while True:
        logging.info("Starting daily post schedule")
        await schedule_forex_posts()
        await schedule_motivation_posts()
        await asyncio.sleep(24 * 3600)  # Wait until next day

# Schedule the morning post
async def start_morning_post():
    while True:
        now = datetime.now()
        if now.hour == 7 and now.minute == 0:
            logging.info("Sending morning post")
            await morning_post()
        await asyncio.sleep(60)

# Schedule the weekend post on Fridays
async def start_weekend_post():
    while True:
        now = datetime.now()
        if now.weekday() == 4 and now.hour == 19 and now.minute == 45:  # Friday 7:45 PM
            logging.info("Sending weekend post")
            await weekend_post()
        await asyncio.sleep(60)

# Set bot commands (optional)
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
    ]
    await bot.set_my_commands(commands)

# Main function to run the bot and schedule
async def main():
    logging.info("Bot is starting...")
    await set_commands(bot)
    
    # Schedule all posts
    logging.info("Scheduling all posts")
    loop = asyncio.get_event_loop()
    loop.create_task(schedule_all_posts())
    loop.create_task(start_morning_post())  # Morning post
    loop.create_task(start_weekend_post())  # Weekend post
    
    # Start polling
    logging.info("Starting polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
