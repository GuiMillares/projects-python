import requests
from colorama import init, Fore, Style, Back, just_fix_windows_console

just_fix_windows_console()
init()

resposta = requests.get("https://zenquotes.io/api/random")
dados = resposta.json()
frase = dados[0]["q"]
autor = dados[0]["a"]

resposta_traducao= requests.get("https://api.mymemory.translated.net/get", params={"q": frase, "langpair": "en|pt"})
dados_traducao = resposta_traducao.json()
frase_traduzida = dados_traducao["responseData"]["translatedText"]

print(Fore.CYAN + f'"{frase_traduzida}"' + Style.RESET_ALL + " — " + Fore.MAGENTA + autor + Style.RESET_ALL)
#print(Fore.GREEN + "Isso fica verde" + Style.RESET_ALL)
# print(f'"{frases}" — {autor}')