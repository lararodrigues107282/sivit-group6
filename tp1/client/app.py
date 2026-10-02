import time, statistics, urllib.request

def measure(url, n=200):
    s = []
    for _ in range(n):
        t = time.perf_counter()
        urllib.request.urlopen(url).read()
        s.append((time.perf_counter() - t) * 1000)
    s.sort()
    return {"p50": s[len(s)//2], "p95": s[int(len(s)*0.95)], "p99": s[int(len(s)*0.99)], "max": s[-1]}

if __name__ == "__main__":
    print("A medir latência para o serviço echo (entre contentores)...")
    print(measure("http://echo:8000/"))