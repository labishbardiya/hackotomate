import urllib.request
import ssl

def test_urllib():
    url = "https://devpost.com/hackathons.rss"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
    )
    
    ctx = ssl._create_unverified_context()
    print("[*] Testing urllib fetch...")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            print(f"[+] Status code: {response.getcode()}")
            print(f"[+] Response preview: {response.read()[:200]}")
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    test_urllib()
