import os
conteudo_corrigido = """def normalize_and_sort_rows(rows, key):
    normalized_rows = [row.copy() for row in rows]
    for row in normalized_rows:
        row[key] = row.get(key, "")
    from operator import getitem
    sorted_rows = sorted(normalized_rows, key=lambda x: getitem(x, key))
    return sorted_rows
rows = [
    {"name": "Alice", "age": 30},
    {"name": "Bob"},
    {"name": "Charlie", "age": 25}
]
sorted_rows = normalize_and_sort_rows(rows, "age")
print(sorted_rows)"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")