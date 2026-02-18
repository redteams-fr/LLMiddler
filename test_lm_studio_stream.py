import requests
import json

url = "http://localhost:8080/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-lm-ZgcV6Qoc:281q1eN2AteVrxgpLhId",
}
payload = {
    "model": "mistralai/ministral-3-3b",
    "messages": [
        {"role": "user", "content": "Quelle est la capitale de la France ?"}
    ],
    "stream": True,
}

response = requests.post(url, headers=headers, json=payload, stream=True)
response.raise_for_status()

for line in response.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data = line[len("data: "):]
    if data == "[DONE]":
        break
    chunk = json.loads(data)
    delta = chunk["choices"][0]["delta"]
    if "content" in delta:
        print(delta["content"], end="", flush=True)

print()
