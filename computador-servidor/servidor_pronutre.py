# -*- coding: utf-8 -*-
"""
Pronutre · programa do computador servidor (o mesmo PC da indústria pode rodar este e o da Goiás Trading)

Sozinho, enquanto o computador estiver ligado:
  1. ANEXOS: copia para o disco cada foto/PDF lançado no ERP Pronutre; depois de alguns dias tira o conteúdo do
     Firebase (plano gratuito). Relatórios (PDF gerados no sistema) vão direto para a pasta relatorios/.
  2. ARQUIVOS ANTIGOS: entrega ao sistema, pela internet (Tailscale Funnel), os anexos que já saíram do Firebase.
     Só para usuário ativo do ERP Pronutre.
  3. CÓPIA DE SEGURANÇA: de hora em hora (8h–18h) copia o que mudou; à noite, cópia completa (guarda 30 dias).
  4. HD EXTERNO: quando o HD marcado (arquivo PRONUTRE-BACKUP.txt na raiz) estiver ligado, copia tudo para ele
     sozinho (no máximo uma vez por hora).
Só biblioteca padrão do Python 3.8+. Configuração em config.ini (mesma pasta).
"""
import base64, configparser, datetime as dt, json, logging, os, socket, string, subprocess, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler

VERSAO = "2026.11.24"
AQUI = os.path.dirname(os.path.abspath(__file__))
COLECOES = ["contratos", "contratosV", "negocios", "cargas", "parceiros", "locais", "motoristas", "corretores", "produtos",
            "tabDesc", "simulacoes", "titulos", "contas", "confs", "comPg", "impAj", "precos", "cobr", "log"]
SEM_UPD = ["usuarios", "config"]          # pequenas e sem campo de data: lidas inteiras
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf", "text/plain": "txt",
       "text/xml": "xml", "application/xml": "xml", "text/html": "html"}
MARCA_HD = "PRONUTRE-BACKUP.txt"

cfg = configparser.ConfigParser()
CFG_ARQ = os.environ.get("PN_CONFIG") or os.path.join(AQUI, "config.ini")
if not cfg.read(CFG_ARQ, encoding="utf-8"):
    print("Não encontrei o config.ini em", CFG_ARQ); sys.exit(1)
API_KEY = cfg.get("firebase", "api_key")
PROJETO = cfg.get("firebase", "projeto", fallback="pronutre-erp")
EMPRESA = cfg.get("firebase", "empresa", fallback="pronutre")
USUARIO = cfg.get("acesso", "email").strip().lower()
SENHA = cfg.get("acesso", "senha")
DESTINO = cfg.get("pastas", "destino")
PORTA = cfg.getint("servidor", "porta", fallback=8788)
PUBLICO = cfg.get("servidor", "endereco_publico", fallback="").strip().rstrip("/")
ORIGENS = [o.strip() for o in cfg.get("servidor", "origens", fallback="https://pronutre-erp.web.app,https://pronutre-erp.firebaseapp.com").split(",") if o.strip()]
DIAS_FB = cfg.getint("anexos", "dias_no_firebase", fallback=5)
HORA_INI = cfg.getint("copia", "hora_inicio", fallback=8)
HORA_FIM = cfg.getint("copia", "hora_fim", fallback=18)
HORA_COMPLETA = cfg.getint("copia", "hora_completa", fallback=2)
INTERVALO = cfg.getint("copia", "intervalo_segundos", fallback=60)
HD_MIN = cfg.getint("hd", "intervalo_minutos", fallback=60)
URL_AUTH = cfg.get("teste", "url_auth", fallback="https://identitytoolkit.googleapis.com/v1")
URL_TOKEN = cfg.get("teste", "url_token", fallback="https://securetoken.googleapis.com/v1")
URL_FS = cfg.get("teste", "url_firestore", fallback="https://firestore.googleapis.com/v1")
RAIZ = f"projects/{PROJETO}/databases/(default)/documents/empresas/{EMPRESA}"
BASE = f"{URL_FS}/{RAIZ}"

for p in ["dados", "completo", "arquivos", "relatorios", "logs"]:
    os.makedirs(os.path.join(DESTINO, p), exist_ok=True)
log = logging.getLogger("pn"); log.setLevel(logging.INFO)
_h = RotatingFileHandler(os.path.join(DESTINO, "logs", "servidor.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s")); log.addHandler(_h)
if sys.stdout and sys.stdout.isatty(): log.addHandler(logging.StreamHandler(sys.stdout))

ESTADO_ARQ = os.path.join(DESTINO, "estado.json")
_trava_estado = threading.Lock()
def ler_estado():
    try:
        with open(ESTADO_ARQ, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def gravar_estado(e):
    with _trava_estado:
        with open(ESTADO_ARQ + ".tmp", "w", encoding="utf-8") as f: json.dump(e, f, ensure_ascii=False, indent=1)
        os.replace(ESTADO_ARQ + ".tmp", ESTADO_ARQ)
def estado(**k):
    e = ler_estado(); e.update(k); gravar_estado(e)
agora_iso = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

# ---------------------------------------------------------------- http / login
def http(metodo, url, corpo=None, token=None, tentativas=3):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    for i in range(tentativas):
        req = urllib.request.Request(url, data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")
        if token: req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                t = r.read(); return json.loads(t) if t else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and i < tentativas - 1: time.sleep(2 * (i + 1)); continue
            raise RuntimeError(f"{metodo} {url.split('?')[0]} → {e.code}: {msg}")
        except (urllib.error.URLError, socket.timeout) as e:
            if i < tentativas - 1: time.sleep(3 * (i + 1)); continue
            raise RuntimeError(f"sem conexão: {e}")
class Sessao:
    def __init__(self): self.token = self.refresh = None; self.ate = 0; self.trava = threading.Lock()
    def obter(self):
        with self.trava:
            if self.token and time.time() < self.ate - 120: return self.token
            if self.refresh:
                try:
                    r = http("POST", f"{URL_TOKEN}/token?key={API_KEY}", {"grant_type": "refresh_token", "refresh_token": self.refresh})
                    self.token, self.refresh, self.ate = r["id_token"], r["refresh_token"], time.time() + int(r.get("expires_in", 3600))
                    return self.token
                except Exception as e: log.warning("renovação do acesso falhou (%s); entrando de novo", e)
            r = http("POST", f"{URL_AUTH}/accounts:signInWithPassword?key={API_KEY}", {"email": USUARIO, "password": SENHA, "returnSecureToken": True})
            self.token, self.refresh, self.ate = r["idToken"], r["refreshToken"], time.time() + int(r.get("expiresIn", 3600))
            log.info("entrou no ERP Pronutre como %s", USUARIO); return self.token
S = Sessao()

# ---------------------------------------------------------------- Firestore (REST)
def de_valor(v):
    for k, f in (("stringValue", str), ("booleanValue", bool), ("doubleValue", float), ("timestampValue", str)):
        if k in v: return f(v[k])
    if "integerValue" in v: return int(v["integerValue"])
    if "mapValue" in v: return {k: de_valor(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "arrayValue" in v: return [de_valor(x) for x in v["arrayValue"].get("values", [])]
    return None
def para_valor(x):
    if x is None: return {"nullValue": None}
    if isinstance(x, bool): return {"booleanValue": x}
    if isinstance(x, int): return {"integerValue": str(x)}
    if isinstance(x, float): return {"doubleValue": x}
    if isinstance(x, dict): return {"mapValue": {"fields": {k: para_valor(v) for k, v in x.items()}}}
    if isinstance(x, list): return {"arrayValue": {"values": [para_valor(v) for v in x]}}
    return {"stringValue": str(x)}
def doc_py(d): return d["name"].rsplit("/", 1)[1], {k: de_valor(v) for k, v in d.get("fields", {}).items()}
def consulta(col, filtros=(), ordem=None, limite=300):
    q = {"from": [{"collectionId": col}], "limit": limite}
    fs = [{"fieldFilter": {"field": {"fieldPath": c}, "op": op, "value": para_valor(v)}} for c, op, v in filtros]
    if len(fs) == 1: q["where"] = fs[0]
    elif fs: q["where"] = {"compositeFilter": {"op": "AND", "filters": fs}}
    if ordem: q["orderBy"] = [{"field": {"fieldPath": ordem}, "direction": "ASCENDING"}]
    r = http("POST", f"{BASE}:runQuery", {"structuredQuery": q}, S.obter())
    return [doc_py(x["document"]) for x in (r if isinstance(r, list) else [r]) if "document" in x]
def listar(col):
    tk = None
    while True:
        r = http("GET", f"{BASE}/{col}?pageSize=300" + (f"&pageToken={urllib.parse.quote(tk)}" if tk else ""), None, S.obter())
        for d in r.get("documents", []): yield doc_py(d)
        tk = r.get("nextPageToken")
        if not tk: break
def ler_doc(col, id_):
    try: return doc_py(http("GET", f"{BASE}/{col}/{urllib.parse.quote(id_, safe='')}", None, S.obter()))[1]
    except RuntimeError as e:
        if "→ 404" in str(e): return None
        raise
def mesclar(col, id_, campos):
    mask = "&".join("updateMask.fieldPaths=" + urllib.parse.quote(k) for k in campos)
    http("PATCH", f"{BASE}/{col}/{urllib.parse.quote(id_, safe='')}?{mask}", {"fields": {k: para_valor(v) for k, v in campos.items()}}, S.obter())
def apagar(col, id_): http("DELETE", f"{BASE}/{col}/{urllib.parse.quote(id_, safe='')}", None, S.obter())

# ---------------------------------------------------------------- 1. anexos e relatórios
def salvar_bin(dest, bruto):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest + ".tmp", "wb") as f: f.write(bruto)
    os.replace(dest + ".tmp", dest)
def nome_seguro(n): return "".join(c if c.isalnum() or c in " .-_()" else "_" for c in (n or "relatorio.html"))[:120]
def caminho_arquivo(id_, ct, em):
    mes = (em or "")[:7] if len(em or "") >= 7 else dt.date.today().strftime("%Y-%m")
    return os.path.join(DESTINO, "arquivos", mes, f"{id_}.{EXT.get(ct, 'bin')}")
def achar_local(id_):
    p = ler_estado().get("indice", {}).get(id_)
    if p and os.path.exists(os.path.join(DESTINO, p)): return os.path.join(DESTINO, p)
    base = os.path.join(DESTINO, "arquivos")
    for mes in sorted(os.listdir(base), reverse=True):
        for n in os.listdir(os.path.join(base, mes)):
            if n.split(".")[0] == id_: return os.path.join(base, mes, n)
    return None
def juntar(id_, d):
    t = d.get("b64") or ""
    for k in range(1, int(d.get("partes") or 1)):
        p = ler_doc("arquivos", f"{id_}__{k}")
        if not p: raise RuntimeError(f"parte {k} do arquivo {id_} não encontrada")
        t += p.get("b64") or ""
    return base64.b64decode(t)
def copiar_anexos():
    n = 0
    while True:
        lote = consulta("arquivos", [("noPc", "EQUAL", False)], limite=40)
        if not lote: break
        e = ler_estado(); idx = e.setdefault("indice", {})
        for id_, d in lote:
            bruto = juntar(id_, d)
            if d.get("rel"):   # relatório: só no PC, sai do Firebase na hora
                dest = os.path.join(DESTINO, "relatorios", (d.get("em") or agora_iso())[:7], f"{(d.get('em') or '')[:10]} {nome_seguro(d.get('nome'))}")
                salvar_bin(dest, bruto)
                for k in range(1, int(d.get("partes") or 1)): apagar("arquivos", f"{id_}__{k}")
                apagar("arquivos", id_); n += 1; continue
            dest = caminho_arquivo(id_, d.get("ct"), d.get("em")); salvar_bin(dest, bruto)
            idx[id_] = os.path.relpath(dest, DESTINO)
            mesclar("arquivos", id_, {"noPc": True, "noPcEm": agora_iso()}); n += 1
        gravar_estado(e)
        if len(lote) < 40: break
    if n: log.info("%d anexo(s)/relatório(s) copiado(s) para o disco", n)
def limpar_firebase():
    limite = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DIAS_FB)).strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    for id_, d in consulta("arquivos", [("limpo", "EQUAL", False)], limite=300):
        if not d.get("noPc") or (d.get("noPcEm") or "9999") > limite: continue
        local = achar_local(id_)
        if not local or (d.get("tam") and os.path.getsize(local) != int(d["tam"])):
            log.warning("anexo %s não está certo no disco; fica no Firebase", id_); continue
        for k in range(1, int(d.get("partes") or 1)):
            try: apagar("arquivos", f"{id_}__{k}")
            except RuntimeError as ex: log.warning("parte %s/%s: %s", id_, k, ex)
        mesclar("arquivos", id_, {"b64": "", "partes": 0, "limpo": True, "limpoEm": agora_iso()}); n += 1
    if n: log.info("%d anexo(s) com mais de %d dias tirado(s) do Firebase (continuam no disco)", n, DIAS_FB)

# ---------------------------------------------------------------- 2. cópia de segurança
def salvar_json(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho + ".tmp", "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False)
    os.replace(caminho + ".tmp", caminho)
def abrir(d):
    """Documentos do ERP guardam o conteúdo em j (JSON); a cópia salva o conteúdo aberto."""
    if isinstance(d.get("j"), str):
        try: return json.loads(d["j"])
        except Exception: pass
    return d
def copia_incremental():
    e = ler_estado(); marcas = e.get("upd", {}); n = 0
    for col in COLECOES:
        campo = "q" if col == "log" else "upd"; ult = marcas.get(col)
        for _ in range(100):
            filtro = [(campo, "GREATER_THAN", ult)] if ult is not None else []
            try: lote = consulta(col, filtro, ordem=campo, limite=500)
            except RuntimeError as ex: log.warning("cópia de %s: %s", col, str(ex)[:200]); break
            for id_, d in lote:
                salvar_json(os.path.join(DESTINO, "dados", col, f"{id_}.json"), abrir(d)); n += 1
                v = d.get(campo)
                if v is not None and (ult is None or v > ult): ult = v
            if len(lote) < 500: break
        if ult is not None: marcas[col] = ult
    for col in SEM_UPD:
        try:
            for id_, d in listar(col): salvar_json(os.path.join(DESTINO, "dados", col, f"{id_}.json"), d); n += 1
        except RuntimeError as ex: log.warning("cópia de %s: %s", col, str(ex)[:200])
    estado(upd=marcas, ultimaIncremental=agora_iso())
    log.info("cópia de hora em hora: %d documento(s)", n)
def locais(col):
    pasta = os.path.join(DESTINO, "dados", col); out = {}
    if os.path.isdir(pasta):
        for n in os.listdir(pasta):
            if n.endswith(".json"):
                try:
                    with open(os.path.join(pasta, n), encoding="utf-8") as f: out[n[:-5]] = json.load(f)
                except Exception: pass
    return out
def copia_completa():
    """Lê o banco inteiro (empresa pequena: cabe no plano gratuito), marca os excluídos e guarda a foto do dia."""
    dia = dt.date.today().isoformat(); pasta = os.path.join(DESTINO, "completo", dia); tot = 0
    for col in COLECOES + SEM_UPD:
        if col == "log": docs = locais(col)          # histórico só cresce: vem da cópia de hora em hora
        else:
            try: docs = {i: (d if col in SEM_UPD else abrir(d)) for i, d in listar(col)}
            except RuntimeError as ex: log.warning("cópia completa de %s: %s", col, ex); continue
            for i, d in docs.items(): salvar_json(os.path.join(DESTINO, "dados", col, f"{i}.json"), d)
            for i in set(locais(col)) - set(docs):
                p = os.path.join(DESTINO, "dados", col, f"{i}.json")
                try: os.replace(p, p + ".excluido")
                except OSError: pass
        salvar_json(os.path.join(pasta, f"{col}.json"), docs); tot += len(docs)
    estado(ultimaCompleta=dia)
    for velha in sorted(os.listdir(os.path.join(DESTINO, "completo")))[:-30]:
        try:
            for n in os.listdir(os.path.join(DESTINO, "completo", velha)): os.remove(os.path.join(DESTINO, "completo", velha, n))
            os.rmdir(os.path.join(DESTINO, "completo", velha))
        except OSError: pass
    log.info("cópia completa do dia %s: %d documento(s)", dia, tot)

# ---------------------------------------------------------------- 3. HD externo automático
def achar_hd():
    if os.name != "nt": return None
    for L in string.ascii_uppercase[3:]:
        if os.path.exists(f"{L}:\\{MARCA_HD}"): return f"{L}:"
    return None
def copia_hd(forcar=False):
    hd = achar_hd()
    if not hd: return False
    e = ler_estado()
    if not forcar and time.time() - e.get("hdEm", 0) < HD_MIN * 60: return False
    dest = os.path.join(hd + "\\", "Pronutre-copias")
    rc = subprocess.call(["robocopy", DESTINO, dest, "/E", "/XO", "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/NJH", "/NJS", "/XF", "*.tmp"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if rc >= 8: log.error("cópia para o HD %s falhou (robocopy %s)", hd, rc); return False
    txt = f"Cópia para o HD {hd} em {dt.datetime.now():%d/%m/%Y %H:%M}"
    with open(os.path.join(DESTINO, "ultima-copia-hd.txt"), "w", encoding="utf-8") as f: f.write(txt)
    with open(os.path.join(dest, "copias-feitas.txt"), "a", encoding="utf-8") as f: f.write(txt + "\n")
    estado(hdEm=time.time(), hdTexto=txt); log.info(txt); return True

# ---------------------------------------------------------------- 4. servidor de arquivos antigos
_verif = {}
def autorizado(token):
    c = _verif.get(token)
    if c and c[1] > time.time(): return c[0]
    ok = False
    try:
        r = http("POST", f"{URL_AUTH}/accounts:lookup?key={API_KEY}", {"idToken": token}, tentativas=1)
        em = (r["users"][0].get("email") or "").lower()
        u = ler_doc("usuarios", em) if em else None
        ok = bool(u and u.get("ativo", "Sim") != "Não")
    except Exception: ok = False
    _verif[token] = (ok, time.time() + 600)
    if len(_verif) > 500:
        for k in list(_verif)[:250]: _verif.pop(k, None)
    return ok
class Arquivos(BaseHTTPRequestHandler):
    server_version = "Pronutre/" + VERSAO
    def log_message(self, *a): pass
    def cors(self):
        o = self.headers.get("Origin", "")
        if o in ORIGENS or "*" in ORIGENS: self.send_header("Access-Control-Allow-Origin", o or "*")
        self.send_header("Vary", "Origin"); self.send_header("Access-Control-Allow-Headers", "Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS"); self.send_header("Access-Control-Max-Age", "86400")
    def fim(self, code): self.send_response(code); self.cors(); self.end_headers()
    def do_OPTIONS(self): self.fim(204)
    def do_GET(self):
        if self.path in ("/", "/saude"):
            self.send_response(200); self.cors(); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
            self.wfile.write(f"Pronutre · computador servidor · {VERSAO} · ok".encode()); return
        if not self.path.startswith("/arquivo/"): return self.fim(404)
        tk = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        if not tk or not autorizado(tk): return self.fim(401)
        id_ = urllib.parse.unquote(self.path.split("/arquivo/", 1)[1]).split("?")[0]
        if not id_.replace("_", "").isalnum(): return self.fim(400)
        local = achar_local(id_)
        if not local: return self.fim(404)
        ct = {v: k for k, v in EXT.items()}.get(local.rsplit(".", 1)[-1], "application/octet-stream")
        with open(local, "rb") as f: b = f.read()
        self.send_response(200); self.cors(); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "private, max-age=86400"); self.end_headers(); self.wfile.write(b)

# ---------------------------------------------------------------- laço principal
def sinal_de_vida():
    e = ler_estado()
    c = {"vistoEm": agora_iso(), "versao": VERSAO, "diasNoFirebase": DIAS_FB, "ultimaCompleta": e.get("ultimaCompleta", ""),
         "ultimaIncremental": e.get("ultimaIncremental", ""), "hd": e.get("hdTexto", "")}
    if PUBLICO: c["url"] = PUBLICO
    mesclar("servidor", "estado", c)
def passo(agora=None):
    agora = agora or dt.datetime.now(); e = ler_estado()
    copiar_anexos()
    if HORA_INI <= agora.hour <= HORA_FIM:
        if e.get("horaIncremental") != agora.strftime("%Y-%m-%d %H"):
            copia_incremental(); estado(horaIncremental=agora.strftime("%Y-%m-%d %H"))
    elif agora.hour >= HORA_COMPLETA and e.get("ultimaCompleta") != agora.date().isoformat():
        copia_incremental(); copia_completa()
    if ler_estado().get("ultimaLimpeza") != agora.date().isoformat():
        limpar_firebase(); estado(ultimaLimpeza=agora.date().isoformat())
    try: copia_hd()
    except Exception as ex: log.warning("HD externo: %s", ex)
    if time.time() - ler_estado().get("sinalEm", 0) > 1800:
        try: sinal_de_vida()
        except Exception as ex: log.warning("sinal de vida: %s", ex)
        estado(sinalEm=time.time())
_ARQ = os.path.abspath(__file__)
_MT0 = os.path.getmtime(_ARQ)
def main():
    try: srv = ThreadingHTTPServer(("0.0.0.0", PORTA), Arquivos)
    except OSError: print("Já está rodando (a porta", PORTA, "está em uso)."); return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("programa iniciado (versão %s). Pasta: %s · porta %d", VERSAO, DESTINO, PORTA)
    if not PUBLICO: log.warning("endereco_publico vazio no config.ini: o sistema não vai buscar anexos antigos aqui")
    while True:
        try: passo()
        except Exception as ex: log.error("falha nesta volta: %s", ex)
        if os.environ.get("PN_UMA_VEZ"): break
        if os.path.getmtime(_ARQ) != _MT0:
            log.info("programa atualizado: encerrando para reabrir com a versão nova"); break
        time.sleep(INTERVALO)
    srv.shutdown()

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    if a == "--completa": copia_incremental(); copia_completa()
    elif a == "--hd": print("Copiado." if copia_hd(forcar=True) else "HD marcado não encontrado (rode marcar-hd.bat).")
    elif a == "--teste":
        print("Entrando no ERP Pronutre…"); S.obter(); print("OK, entrou como", USUARIO)
        print("Anexos aguardando cópia:", len(consulta("arquivos", [("noPc", "EQUAL", False)], limite=40)))
    else: main()
