import httpx

def test_headers():
    url = "https://devpost.com/hackathons.rss"
    # Try fully loaded browser headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }
    
    print("[*] Testing httpx fetch with browser headers...")
    try:
        response = httpx.get(url, headers=headers, verify=False, timeout=10)
        print(f"[+] Status code: {response.status_code}")
        print(f"[+] Response preview: {response.text[:200]}")
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    test_headers()
