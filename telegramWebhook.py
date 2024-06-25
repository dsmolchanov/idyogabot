import requests

BOT_TOKEN = "6859846019:AAHhrnhKY0Iui2rNXGLN2hVrb6LItjf-PwY"
WEBHOOK_URL = f"https://idyogabot-production.up.railway.app/{BOT_TOKEN}"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}"

response = requests.get(url)

if response.status_code == 200:
    print("Webhook set successfully.")
else:
    print("Failed to set webhook:", response.text)
