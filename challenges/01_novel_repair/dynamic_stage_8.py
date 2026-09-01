import os
conteudo_corrigido = """from copy import deepcopy
def normalize_and_sort_rows(rows, key):
    rows_copy = deepcopy(rows)
    for row in rows_copy:
        if row.get(key) is None or row.get(key) == '':
            row[key] = ''
    sorted_rows = sorted(rows_copy, key=lambda x: (x.get(key) != '', x.get(key)))
    return sorted_rows
if __name__ == "__main__":
    rows = [
        {'id': 1, 'name': 'Alice'},
        {'id': 2},
        {'id': 3, 'name': 'Bob'},
        {'id': 4, 'name': ''}
    ]
    key = 'name'
    sorted_rows = normalize_and_sort_rows(rows, key)
    print(sorted_rows)"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")