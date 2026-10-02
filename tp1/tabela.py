import time, urllib.request

def medir_funcao(n=200):
    s = []
    def funcao_vazia(): pass
    for _ in range(n):
        t = time.perf_counter()
        funcao_vazia()
        s.append((time.perf_counter() - t) * 1000)
    s.sort()
    return {"p50": round(s[len(s)//2], 4), "p95": round(s[int(len(s)*0.95)], 4), "p99": round(s[int(len(s)*0.99)], 4)}

def medir_http(url, n=30):
    s = []
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    for _ in range(n):
        t = time.perf_counter()
        try:
            urllib.request.urlopen(req, timeout=5).read()
            s.append((time.perf_counter() - t) * 1000)
        except Exception:
            pass # Ignora bloqueios temporários e continua
            
    if not s:
        return "Erro ao contactar servidor"
    s.sort()
    return {"p50": round(s[len(s)//2], 2), "p95": round(s[int(len(s)*0.95)], 2), "p99": round(s[int(len(s)*0.99)], 2)}

print("1. Local function call:", medir_funcao())
print("2. HTTP to localhost:", medir_http("http://localhost:8000/", 200))
print("3. HTTP to Portugal (UP):", medir_http("https://www.up.pt", 30))
print("4. HTTP to USA (Example):", medir_http("http://example.com", 30))