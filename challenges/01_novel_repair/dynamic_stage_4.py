import os
conteudo_corrigido = """# fixture/src/orders.py
import copy
def sort_orders(rows, key):
    rows_copy = [dict(r) for r in rows]
    presentes = [r for r in rows_copy if key in r]
    ausentes = [r for r in rows_copy if key not in r]
    for row in presentes:
        if row[key] is None:
            row[key] = ''
    sorted_presentes = sorted(presentes, key=lambda r: r.get(key, ''))
    result = sorted_presentes + ausentes
    return result
original_rows = [
    {'key1': 'value1', 'key2': 'value2'},
    {'key1': None},
    {'key2': 'value3'}
]
sorted_rows = sort_orders(original_rows, 'key1')
print(sorted_rows)"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")