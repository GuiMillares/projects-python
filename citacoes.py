import requests

resposta = requests.get("https://zenquotes.io/api/random")
dados = resposta.json()
frases = dados[0]["q"]
autor = dados[0]["a"]

print(f'"{frases}" — {autor}')