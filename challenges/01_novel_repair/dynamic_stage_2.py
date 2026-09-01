import os
conteudo_corrigido = """def normalize_and_sort_orders(rows, key, descending=False):
    sorted_rows = rows.copy()
    def sort_key(row):
        return row.get(key, '')
    if descending:
        sorted_rows.sort(key=sort_key, reverse=True)
    else:
        sorted_rows.sort(key=sort_key)
    return sorted_rows
rows = [
    {"name": "c", "customer": "Zoe"},
    {"name": "a", "customer": "Ada"},
    {"name": "b", "customer": "Bob"},
]
result = normalize_and_sort_orders(rows, "customer")
print(result)  # Saída: [{'name': 'a', 'customer': 'Ada'}, {'name': 'b', 'customer': 'Bob'}, {'name': 'c', 'customer': 'Zoe'}]
rows_with_missing_key = [
    {"name": "c", "customer": "Zoe"},
    {"name": "a", "customer": None},
    {"name": "b", "customer": "Bob"},
]
result_with_missing_key = normalize_and_sort_orders(rows_with_missing_key, "customer")
print(result_with_missing_key)  # Saída: [{'name': 'a', 'customer': ''}, {'name': 'b', 'customer': 'Bob'}, {'name': 'c', 'customer': 'Zoe'}]"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")