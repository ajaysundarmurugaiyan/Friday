"""
Run this script ONCE to authenticate your Gmail account.
It will open a browser, ask you to login to Google, and save a token.json file.
After that, the Friday agent will use token.json automatically — no browser needed again.

Usage:
    python gmail_auth.py
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print("\n❌ ERROR: credentials.json not found!")
        print(f"   Expected at: {CREDENTIALS_FILE}")
        print("\n   → Go to Google Cloud Console → APIs & Services → Credentials")
        print("   → Download your OAuth 2.0 Client ID JSON")
        print("   → Save it as 'credentials.json' in this folder\n")
        return

    creds = None

    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid token, do the browser login flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🌐 Opening browser for Google login...")
            print("   → Login with: ceitajaysundar25@gmail.com\n")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        print(f"\n✅ token.json saved to: {TOKEN_FILE}")

    print("\n🎉 Gmail OAuth authentication successful!")
    print("   Friday will now send emails using Gmail API (HTTPS — no SMTP ports needed).")
    print("   You don't need to run this script again unless the token expires.\n")


if __name__ == "__main__":
    main()
