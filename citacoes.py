import requests

resposta = requests.get("https://zenquotes.io/api/random")
dados = resposta.json()
frase = dados[0]["q"]
autor = dados[0]["a"]

resposta_traducao= requests.get("https://api.mymemory.translated.net/get", params={"q": frase, "langpair": "en|pt"})
dados_traducao = resposta_traducao.json()
frase_traduzida = dados_traducao["responseData"]["translatedText"]

print(f'"{frase_traduzida}" — {autor}')
# print(f'"{frases}" — {autor}')