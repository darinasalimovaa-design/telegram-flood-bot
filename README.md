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
2. Copy `.env.example` to `.env` and set:
   - `BOT_TOKEN`
   - `WEBHOOK_BASE_URL` (for PythonAnywhere domain, e.g. `https://yourname.pythonanywhere.com`)
   - `WEBHOOK_SECRET` (strongly recommended; primary webhook request validation mechanism)
   - optional `WEBHOOK_PATH` (default: `/webhook`; changing to a random path provides defense-in-depth against automated scanners)
3. Update `config.json` with:
   - `main_admin_id`
   - `admin_group_id`
   - both chat IDs
   - info links
4. Register webhook in Telegram:
   ```bash
   python set_webhook.py
   ```

## PythonAnywhere deployment (webhook)
1. Create a Python web app on PythonAnywhere (manual or Flask config).
2. Configure virtualenv and install dependencies from `requirements.txt`.
3. Set environment variables in the web app (or in `.env` loaded from project directory).
4. In WSGI file, point to project and Flask app:
   ```python
   import sys
   path = "/home/<your_pythonanywhere_username>/telegram-flood-bot"
   if path not in sys.path:
       sys.path.append(path)

   from app import app as application
   ```
   Replace `telegram-flood-bot` with your actual project directory name on PythonAnywhere.
5. Reload web app in PythonAnywhere dashboard.
6. Run webhook registration once:
   ```bash
   python set_webhook.py
   ```

Webhook endpoint is served by `app.py` on `WEBHOOK_PATH`.
