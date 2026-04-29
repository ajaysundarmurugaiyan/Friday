#!/usr/bin/env python3
"""
Simple script to generate a LiveKit access token for testing
"""
from livekit import api
import os
from dotenv import load_dotenv

load_dotenv()

def generate_token(room_name="friday-room", participant_name="test-user"):
    """Generate a LiveKit access token"""
    
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")
    
    if not api_key or not api_secret:
        print("❌ Error: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in .env file")
        return None
    
    # Create access token
    token = api.AccessToken(api_key, api_secret)
    token.with_identity(participant_name)
    token.with_name(participant_name)
    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )
    )
    
    jwt_token = token.to_jwt()
    
    print("\n" + "="*60)
    print("✅ LiveKit Access Token Generated Successfully!")
    print("="*60)
    print(f"\n📍 LiveKit URL: {livekit_url}")
    print(f"🏠 Room Name: {room_name}")
    print(f"👤 Participant: {participant_name}")
    print(f"\n🔑 Token:\n{jwt_token}")
    print("\n" + "="*60)
    print("\n📝 How to use:")
    print("1. Go to: https://meet.livekit.io/custom")
    print(f"2. Enter URL: {livekit_url}")
    print("3. Paste the token above")
    print("4. Click 'Connect'")
    print("5. Your Friday agent should join automatically!")
    print("="*60 + "\n")
    
    return jwt_token

if __name__ == "__main__":
    generate_token()
