import os
conteudo_corrigido = """import copy
def normalize_and_sort_rows(rows, key):
    rows_copy = copy.deepcopy(rows)
    normalized_rows = []
    for row in rows_copy:
        normalized_row = {k: v.get(key, '') if isinstance(v, dict) else v.get(key, '') for k, v in row.items()}
        normalized_rows.append(normalized_row)
    def custom_sort(item):
        value = item.get(key, '')
        return (value == '', value)
    sorted_rows = sorted(normalized_rows, key=custom_sort)
    return sorted_rows"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")