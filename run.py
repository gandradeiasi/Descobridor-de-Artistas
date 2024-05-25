import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
import logging

# Configuração do log
logging.basicConfig(filename='artistas_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

class SpotifyManager:
    def __init__(self, client_id, client_secret, redirect_uri, scope, artistas_txt, artistas_potenciais_txt):
        self.auth_manager = SpotifyOAuth(client_id=client_id,
                                         client_secret=client_secret,
                                         redirect_uri=redirect_uri,
                                         scope=scope,
                                         open_browser=True)
        self.spotify = spotipy.Spotify(auth_manager=self.auth_manager, requests_timeout=10)
        self.artistas_txt = artistas_txt
        self.artistas_potenciais_txt = artistas_potenciais_txt
        self.artistas = self.carregar_artistas(self.artistas_txt)
    
    def carregar_artistas(self, file_path):
        if not os.path.exists(file_path):
            return {}
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            linhas = file.readlines()
        artistas = {}
        for linha in linhas:
            partes = linha.strip().split('|')
            if len(partes) == 4:
                id, nome, status, relacionados = partes
                generos = '[]'  # Lista vazia para os gêneros se não estiver presente
            elif len(partes) == 5:
                id, nome, status, relacionados, generos = partes
            else:
                continue  # Ignorar linhas que não possuem o formato correto
            artistas[id] = {
                'nome': nome,
                'status': status,
                'relacionados': json.loads(relacionados),
                'generos': json.loads(generos)
            }
        return artistas

    def salvar_artistas(self):
        with open(self.artistas_txt, 'w', encoding='utf-8') as file:
            for id, dados in self.artistas.items():
                file.write(f"{id}|{dados['nome']}|{dados['status']}|{json.dumps(dados['relacionados'])}|{json.dumps(dados['generos'])}\n")

    def salvar_artistas_potenciais(self):
        with open(self.artistas_potenciais_txt, 'w', encoding='utf-8') as file:
            for id, dados in self.artistas.items():
                if dados['status'] == '*':
                    file.write(f"{dados['nome']}\n")

    def adicionar_artista(self, id, nome, status, generos):
        if id not in self.artistas:
            self.artistas[id] = {'nome': nome, 'status': status, 'relacionados': [], 'generos': generos}

    def obter_artistas_seguidos(self):
        artistas = []
        results = self.spotify.current_user_followed_artists(limit=50)
        while results:
            artistas.extend([(artista['id'], artista['name']) for artista in results['artists']['items']])
            if results['artists']['next']:
                results = self.spotify.next(results['artists'])
            else:
                results = None
        return artistas

    def adicionar_candidatos_novos(self):
        novos_artistas = self.obter_artistas_seguidos()
        novos_adicionados = False
        for id, nome in novos_artistas:
            if id not in self.artistas:
                artista = self.spotify.artist(id)
                generos = artista['genres']
                self.adicionar_artista(id, nome, '', generos)
                novos_adicionados = True
        self.salvar_artistas()
        if not novos_adicionados:
            print("Nenhum novo artista foi adicionado.")
            input("Pressione qualquer tecla para continuar.")

    def obter_artistas_relacionados(self, artista_id):
        try:
            resultados = self.spotify.artist_related_artists(artista_id)
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

    def atualizar_relacionados(self, artista_id):
        relacionados = self.obter_artistas_relacionados(artista_id)
        self.artistas[artista_id]['relacionados'] = relacionados
        for rel_id in relacionados:
            if rel_id not in self.artistas:
                try:
                    artista = self.spotify.artist(rel_id)
                    nome = artista['name']
                    generos = artista['genres']
                    self.adicionar_artista(rel_id, nome, '', generos)
                except spotipy.SpotifyException as e:
                    if e.http_status == 429:
                        retry_after = int(e.headers.get('Retry-After', 10))
                        print(f'Rate limit exceeded. Wait for {retry_after} seconds.')
                        logging.warning(f'Rate limit exceeded for artist ID: {rel_id}. Wait for {retry_after} seconds.')
                        input("Pressione qualquer tecla para fechar a aplicação.")
                        exit()
                    logging.error(f'Erro ao adicionar artista relacionado ID: {rel_id} - {str(e)}')

    def atualizar_status(self, artista_id, status):
        if artista_id in self.artistas:
            self.artistas[artista_id]['status'] = status
            candidatos = [id for id, dados in self.artistas.items() if dados['status'] == '']
            quantidade_candidatos = len(candidatos)
            if status == '+' or quantidade_candidatos == 1:
                self.atualizar_relacionados(artista_id)

    def listar_artistas_com_potencial(self):
        for id, dados in self.artistas.items():
            if dados['status'] == '*':
                print(f"{dados['nome']} (ID: {id})")

    def identificar_potenciais(self):
        candidatos_potenciais = [
            (id, [artista_id for artista_id, artista in self.artistas.items() if artista['status'] == '+' and id in artista['relacionados']])
            for id, dados in self.artistas.items()
            if dados['status'] == '=' and len([artista_id for artista_id, artista in self.artistas.items() if artista['status'] == '+' and id in artista['relacionados']]) == 2
        ]

        pares_positivos_contagem = {}
        for id, relacionados_positivos in candidatos_potenciais:
            relacionados_positivos_tuple = tuple(relacionados_positivos)
            pares_positivos_contagem[relacionados_positivos_tuple] = pares_positivos_contagem.get(relacionados_positivos_tuple, 0) + 1

        for id, relacionados_positivos in candidatos_potenciais:
            relacionados_positivos_tuple = tuple(relacionados_positivos)
            if pares_positivos_contagem[relacionados_positivos_tuple] == 1:
                self.artistas[id]['status'] = '*'
                print(f"O artista {self.artistas[id]['nome']} tem potencial. Referenciado por: {', '.join([self.artistas[artista_id]['nome'] for artista_id in relacionados_positivos])}")

    def reverter_potenciais(self):
        candidatos_potenciais = [
            (id, [artista_id for artista_id, artista in self.artistas.items() if artista['status'] == '+' and id in artista['relacionados']])
            for id, dados in self.artistas.items()
            if dados['status'] == '*' and len([artista_id for artista_id, artista in self.artistas.items() if artista['status'] == '+' and id in artista['relacionados']]) == 2
        ]

        pares_positivos_contagem = {}
        for id, relacionados_positivos in candidatos_potenciais:
            relacionados_positivos_tuple = tuple(relacionados_positivos)
            pares_positivos_contagem[relacionados_positivos_tuple] = pares_positivos_contagem.get(relacionados_positivos_tuple, 0) + 1

        for id, dados in self.artistas.items():
            if dados['status'] == '*':
                relacionados_positivos = [artista_id for artista_id, artista in self.artistas.items() if artista['status'] == '+' and id in artista['relacionados']]
                relacionados_positivos_tuple = tuple(relacionados_positivos)
                if len(relacionados_positivos) != 2 or pares_positivos_contagem.get(relacionados_positivos_tuple, 0) > 1:
                    self.artistas[id]['status'] = '='
                    print(f"O artista {self.artistas[id]['nome']} não é mais potencial e foi revertido para =. Referenciado por: {', '.join([self.artistas[artista_id]['nome'] for artista_id in relacionados_positivos])}")

def main():
    # Inicializando o SpotifyManager
    spotify_manager = SpotifyManager(
        client_id='20f85615d27a4489930e38aea58e2039',
        client_secret='d323e63572d34a8082c300d3a8ea7364',
        redirect_uri='https://localhost',
        scope='user-follow-read',
        artistas_txt='artistas.txt',
        artistas_potenciais_txt='artistas_potenciais.txt'
    )
    
    # Identificar e reverter potenciais no início do programa
    spotify_manager.identificar_potenciais()
    spotify_manager.reverter_potenciais()
    spotify_manager.salvar_artistas()
    spotify_manager.salvar_artistas_potenciais()
    
    while True:
        candidatos = [id for id, dados in spotify_manager.artistas.items() if dados['status'] == '']
        if not candidatos:
            spotify_manager.adicionar_candidatos_novos()
            candidatos = [id for id, dados in spotify_manager.artistas.items() if dados['status'] == '']
            if not candidatos:
                break
        artista_id = candidatos[0]
        try:
            artista = spotify_manager.spotify.artist(artista_id)
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
        
        print(f"Artista: {artista['name']} | {', '.join(artista['genres'])}")
        comando = input("Digite +, - ou =: ")
        if comando == '*':
            spotify_manager.identificar_potenciais()
            spotify_manager.reverter_potenciais()
            spotify_manager.salvar_artistas_potenciais()
            continue
        elif comando == '/':
            spotify_manager.adicionar_candidatos_novos()
            continue
        spotify_manager.atualizar_status(artista_id, comando)
        spotify_manager.salvar_artistas()
    
    while True:
        comando = input("Digite * para listar artistas com potencial, ou q para sair: ")
        if comando == '*':
            spotify_manager.listar_artistas_com_potencial()
        elif comando == 'q':
            break

if __name__ == "__main__":
    main()
