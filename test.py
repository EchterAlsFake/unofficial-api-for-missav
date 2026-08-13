from curl_cffi import requests

# Create a session so cookies persist
session = requests.Session(impersonate="chrome124")

# Set the cookies obtained from your browser inspect session
# (Replace with your actual _cf_bm and cf_clearance if present)


headers = {

}

# Request the video segment disguised as a .jpeg
url = "https://surrit.com/9320047d-bf16-463f-9943-b61d6406c1f5/640x360/video3.jpeg"

response = session.get(
    url,
    headers=headers,
    timeout=10 # If configured properly, it will respond in < 1 sec
)

print(f"Status Code: {response.status_code}")
print(f"Downloaded {len(response.content)} bytes")

# Save as actual video/ts file
with open("video3.ts", "wb") as f:
    f.write(response.content)