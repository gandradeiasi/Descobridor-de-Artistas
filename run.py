import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
import logging

# Configuração do log
logging.basicConfig(filename='artistas_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

# Credenciais de autenticação
CLIENT_ID = '20f85615d27a4489930e38aea58e2039'
CLIENT_SECRET = 'd323e63572d34a8082c300d3a8ea7364'
REDIRECT_URI = 'https://localhost'

# Configuração da autenticação do usuário
SCOPE = 'user-follow-read'
AUTH_MANAGER = SpotifyOAuth(client_id=CLIENT_ID,
                            client_secret=CLIENT_SECRET,
                            redirect_uri=REDIRECT_URI,
                            scope=SCOPE,
                            open_browser=True)
SPOTIFY = spotipy.Spotify(auth_manager=AUTH_MANAGER, requests_timeout=10)

# Nome dos arquivos
ARTISTAS_TXT = 'artistas.txt'
ARTISTAS_POTENCIAIS_TXT = 'artistas_potenciais.txt'

def carregar_artistas(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        linhas = file.readlines()
    return {id: {'nome': nome, 'status': status, 'relacionados': json.loads(relacionados)}
            for linha in linhas
            for id, nome, status, relacionados in [linha.strip().split('|')]}

def salvar_artistas(artistas, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        for id, dados in artistas.items():
            file.write(f"{id}|{dados['nome']}|{dados['status']}|{json.dumps(dados['relacionados'])}\n")

def salvar_artistas_potenciais(artistas, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        for id, dados in artistas.items():
            if dados['status'] == '*':
                file.write(f"{id}|{dados['nome']}\n")

def adicionar_artista(artistas, id, nome, status):
    if id not in artistas:
        artistas[id] = {'nome': nome, 'status': status, 'relacionados': []}

def obter_artistas_seguidos(spotify_client):
    artistas = []
    results = spotify_client.current_user_followed_artists(limit=50)
    while results:
        artistas.extend([(artista['id'], artista['name']) for artista in results['artists']['items']])
        if results['artists']['next']:
            results = spotify_client.next(results['artists'])
        else:
            results = None
    return artistas

def adicionar_candidatos_novos(artistas, spotify_client):
    novos_artistas = obter_artistas_seguidos(spotify_client)
    novos_adicionados = False
    for id, nome in novos_artistas:
        if id not in artistas:
            adicionar_artista(artistas, id, nome, '')
            novos_adicionados = True
    salvar_artistas(artistas, ARTISTAS_TXT)
    if not novos_adicionados:
        print("Nenhum novo artista foi adicionado.")
        input("Pressione qualquer tecla para fechar a aplicação.")

def obter_artistas_relacionados(spotify_client, artista_id):
    try:
        resultados = spotify_client.artist_related_artists(artista_id)
        return [artista['id'] for artista in resultados['artists']]
    except spotipy.SpotifyException as e:
        if e.http_status == 429:
            retry_after = int(e.headers.get('Retry-After', 10))
            print(f'Rate limit exceeded. Wait for {retry_after} seconds.')
            logging.warning(f'Rate limit exceeded for artist ID: {artista_id}. Wait for {retry_after} seconds.')
            input("Pressione qualquer tecla para fechar a aplicação.")
            exit()
        logging.error(f'Erro ao buscar artistas relacionados para o artista ID: {artista_id} - {str(e)}')
        return []

def atualizar_relacionados(artistas, spotify_client, artista_id):
    relacionados = obter_artistas_relacionados(spotify_client, artista_id)
    artistas[artista_id]['relacionados'] = relacionados
    for rel_id in relacionados:
        if rel_id not in artistas:
            try:
                nome = spotify_client.artist(rel_id)['name']
                adicionar_artista(artistas, rel_id, nome, '')
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', 10))
                    print(f'Rate limit exceeded. Wait for {retry_after} seconds.')
                    logging.warning(f'Rate limit exceeded for artist ID: {rel_id}. Wait for {retry_after} seconds.')
                    input("Pressione qualquer tecla para fechar a aplicação.")
                    exit()
                logging.error(f'Erro ao adicionar artista relacionado ID: {rel_id} - {str(e)}')

def atualizar_status(artistas, spotify_client, artista_id, status):
    if artista_id in artistas:
        artistas[artista_id]['status'] = status
        candidatos = [id for id, dados in artistas.items() if dados['status'] == '']
        quantidade_cantidatos = len(candidatos)
        if status == '+' or quantidade_cantidatos == 1:
            atualizar_relacionados(artistas, spotify_client, artista_id)

def listar_artistas_com_potencial(artistas):
    for id, dados in artistas.items():
        if dados['status'] == '*':
            print(f"{dados['nome']} (ID: {id})")

def identificar_potenciais(artistas):
    candidatos_potenciais = [
        (id, [artista_id for artista_id, artista in artistas.items() if artista['status'] == '+' and id in artista['relacionados']])
        for id, dados in artistas.items()
        if dados['status'] == '=' and len([artista_id for artista_id, artista in artistas.items() if artista['status'] == '+' and id in artista['relacionados']]) == 2
    ]

    pares_positivos_contagem = {}
    for id, relacionados_positivos in candidatos_potenciais:
        relacionados_positivos_tuple = tuple(relacionados_positivos)
        pares_positivos_contagem[relacionados_positivos_tuple] = pares_positivos_contagem.get(relacionados_positivos_tuple, 0) + 1

    for id, relacionados_positivos in candidatos_potenciais:
        relacionados_positivos_tuple = tuple(relacionados_positivos)
        if pares_positivos_contagem[relacionados_positivos_tuple] == 1:
            artistas[id]['status'] = '*'
            print(f"O artista {artistas[id]['nome']} tem potencial. Referenciado por: {', '.join([artistas[artista_id]['nome'] for artista_id in relacionados_positivos])}")

def reverter_potenciais(artistas):
    candidatos_potenciais = [
        (id, [artista_id for artista_id, artista in artistas.items() if artista['status'] == '+' and id in artista['relacionados']])
        for id, dados in artistas.items()
        if dados['status'] == '*' and len([artista_id for artista_id, artista in artistas.items() if artista['status'] == '+' and id in artista['relacionados']]) == 2
    ]

    pares_positivos_contagem = {}
    for id, relacionados_positivos in candidatos_potenciais:
        relacionados_positivos_tuple = tuple(relacionados_positivos)
        pares_positivos_contagem[relacionados_positivos_tuple] = pares_positivos_contagem.get(relacionados_positivos_tuple, 0) + 1

    for id, dados in artistas.items():
        if dados['status'] == '*':
            relacionados_positivos = [artista_id for artista_id, artista in artistas.items() if artista['status'] == '+' and id in artista['relacionados']]
            relacionados_positivos_tuple = tuple(relacionados_positivos)
            if len(relacionados_positivos) != 2 or pares_positivos_contagem.get(relacionados_positivos_tuple, 0) > 1:
                artistas[id]['status'] = '='
                print(f"O artista {artistas[id]['nome']} não é mais potencial e foi revertido para =. Referenciado por: {', '.join([artistas[artista_id]['nome'] for artista_id in relacionados_positivos])}")

def main():
    artistas = carregar_artistas(ARTISTAS_TXT)
    
    # Identificar e reverter potenciais no início do programa
    identificar_potenciais(artistas)
    reverter_potenciais(artistas)
    salvar_artistas(artistas, ARTISTAS_TXT)
    salvar_artistas_potenciais(artistas, ARTISTAS_POTENCIAIS_TXT)
    
    while True:
        candidatos = [id for id, dados in artistas.items() if dados['status'] == '']
        if not candidatos:
            adicionar_candidatos_novos(artistas, SPOTIFY)
            candidatos = [id for id, dados in artistas.items() if dados['status'] == '']
            if not candidatos:
                break
        artista_id = candidatos[0]
        try:
            artista = SPOTIFY.artist(artista_id)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get('Retry-After', 10))
                print(f'Rate limit exceeded. Wait for {retry_after} seconds.')
                logging.warning(f'Rate limit exceeded for artist ID: {artista_id}. Wait for {retry_after} seconds.')
                input("Pressione qualquer tecla para fechar a aplicação.")
                exit()
            continue
        except Exception:
            continue
        
        print(f"Artista: {artista['name']} | Restam {len(candidatos) - 1} artistas para classificar")
        comando = input("Digite +, - ou =: ")
        if comando == '*':
            listar_artistas_com_potencial(artistas)
            continue
        atualizar_status(artistas, SPOTIFY, artista_id, comando)
        identificar_potenciais(artistas)
        reverter_potenciais(artistas)
        salvar_artistas(artistas, ARTISTAS_TXT)
        salvar_artistas_potenciais(artistas, ARTISTAS_POTENCIAIS_TXT)
    
    while True:
        comando = input("Digite * para listar artistas com potencial, ou q para sair: ")
        if comando == '*':
            listar_artistas_com_potencial(artistas)
        elif comando == 'q':
            break

if __name__ == "__main__":
    main()
