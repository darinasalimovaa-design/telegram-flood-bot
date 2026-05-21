# Telegram Flood Admission Bot

Python bot for managing admission to two Telegram chats with file-based storage, admin moderation, reservation flow, one-time invite links, and access confirmation.

## Features
- Two-chat selection flow
- Application form with Telegram ID, username, role, birth date, and code word
- Admin approval / rejection
- Optional rejection feedback
- One-time invite links for approved users
- Access confirmation step before notifying admins
- Reservation flow when a chat is full
- Full application and reservation lists in private admin chat and admin group
- JSON file storage instead of a database
- Logging to file
- Admin commands in group: `/applications`, `/reservations`, `/pending`, `/status`

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set your bot token.
3. Update `config.json` with:
   - `main_admin_id`
   - `admin_group_id`
   - both chat IDs
   - info links
4. Run the bot:
   ```bash
   python bot.py
   ```
