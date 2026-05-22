import os
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from backend.discovery import discover_new_hackathons_async
import asyncio

async def test():
    print("[*] Running discovery test...")
    print(f"DISCOVERY_FEEDS env: {os.getenv('DISCOVERY_FEEDS')}")
    try:
        urls = await discover_new_hackathons_async()
        print(f"[+] Successfully discovered {len(urls)} URLs!")
        for idx, u in enumerate(urls[:5]):
            print(f"  {idx + 1}: {u}")
    except Exception as e:
        print(f"[!] Critical error during discovery: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
