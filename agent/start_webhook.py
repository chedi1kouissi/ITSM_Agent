# start_webhook.py
"""
Starts the ITSM Agent webhook server with a live ngrok tunnel.

Usage:
    python start_webhook.py

What this does:
  1. Opens a public ngrok HTTPS tunnel on port 8001.
  2. Prints the public URL — copy the /webhook/linear path into Linear settings.
  3. Launches the FastAPI webhook server (uvicorn) on localhost:8001.

Prerequisites:
  - pip install pyngrok uvicorn fastapi
  - Set NGROK_AUTHTOKEN in .env (get one free at https://dashboard.ngrok.com)
  - Set LINEAR_WEBHOOK_SECRET in .env after registering the URL in Linear.

Linear webhook setup (one-time):
  1. Run this script and copy the printed URL.
  2. Go to Linear → Settings → Administration → API → Webhooks → New Webhook.
  3. Paste URL + /webhook/linear as the endpoint.
  4. Enable event: Comments (Create).
  5. Copy the Signing Secret Linear shows you.
  6. Paste it as LINEAR_WEBHOOK_SECRET in your .env file.
  7. Restart this script — signature verification will now be active.
"""

import os
import sys
import subprocess
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_PORT = 8001


def main():
    try:
        from pyngrok import ngrok, conf
    except ImportError:
        print("❌ pyngrok is not installed. Run: pip install pyngrok")
        sys.exit(1)

    # Configure ngrok auth token if provided
    ngrok_token = os.getenv("NGROK_AUTHTOKEN", "")
    if ngrok_token:
        conf.get_default().auth_token = ngrok_token
    else:
        print(
            "⚠️  NGROK_AUTHTOKEN not set in .env.\n"
            "   Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken\n"
            "   Add it as: NGROK_AUTHTOKEN=<your_token>\n"
        )

    # Open the tunnel
    print(f"🚇 Opening ngrok tunnel on port {WEBHOOK_PORT}...")
    tunnel = ngrok.connect(WEBHOOK_PORT, "http")
    public_url = tunnel.public_url

    print("\n" + "=" * 60)
    print("🌐  Ngrok tunnel is LIVE")
    print("=" * 60)
    print(f"\n   Public URL  : {public_url}")
    print(f"   Webhook URL : {public_url}/webhook/linear")
    print(f"\n📋  Linear setup (one-time):")
    print(f"   1. Go to Linear → Settings → API → Webhooks → New Webhook")
    print(f"   2. Endpoint URL : {public_url}/webhook/linear")
    print(f"   3. Enable event : Comments (Create)")
    print(f"   4. Copy the Signing Secret → add to .env as LINEAR_WEBHOOK_SECRET")
    print(f"\n⚠️  This URL changes every restart unless you have a paid ngrok plan.")
    print("=" * 60 + "\n")

    # Launch uvicorn
    try:
        subprocess.run(
            [
                sys.executable, "-m", "uvicorn",
                "webhook_server:app",
                "--host", "0.0.0.0",
                "--port", str(WEBHOOK_PORT),
                "--reload",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 Webhook server stopped.")
    finally:
        print("🔌 Closing ngrok tunnel...")
        ngrok.disconnect(public_url)
        ngrok.kill()


if __name__ == "__main__":
    main()
