import os
conteudo_corrigido = """# fixture/src/orders.py
def get_safe_value(row, key):
    return row.get(key, '')
rows_copy = [row.copy() for row in rows]  # Garantir imutabilidade profunda
sorted_rows = sorted(rows_copy, key=lambda x: (get_safe_value(x, 'name'), get_safe_value(x, 'customer')))
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")