import urllib.request
import ssl

def test_accept_headers():
    url = "https://devpost.com/hackathons.rss"
    
    options = [
        {"Accept": "application/rss+xml, application/xml, text/xml"},
        {"Accept": "text/xml"},
        {"Accept": "application/rss+xml"},
        {"Accept": "*/*"},
    ]
    
    ctx = ssl._create_unverified_context()
    
    for idx, opt in enumerate(options):
        print(f"[*] Option {idx + 1}: testing headers {opt}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        headers.update(opt)
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                print(f"  [+] SUCCESS! Status code: {response.getcode()}")
                print(f"  [+] Preview: {response.read()[:100]}")
                return
        except Exception as e:
            print(f"  [-] Failed: {e}")

if __name__ == "__main__":
    test_accept_headers()
