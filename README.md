# GK GS Telegram Quiz Bot — GitHub

This package contains the working Telegram quiz bot plus a GitHub Actions workflow.

IMPORTANT:
GitHub-hosted Actions jobs have a maximum execution time of 6 hours, so GitHub Actions is NOT guaranteed 24/7 hosting for this polling bot.

Setup:
1. Create a GitHub repository.
2. Upload all files from this ZIP.
3. In Settings -> Secrets and variables -> Actions, create:
   TELEGRAM_BOT_TOKEN
   OPENAI_API_KEY
4. Open Actions -> Telegram Quiz Bot -> Run workflow.
5. Open Telegram and send /start, then send a clear book/PDF page photo.

Never put your Telegram token or OpenAI key directly into the repository.
