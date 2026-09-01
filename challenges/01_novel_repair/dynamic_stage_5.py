import os
conteudo_corrigido = """# Import necessary libraries
import copy
def normalize_and_sort_orders(rows):
    """
    Normalize and sort the list of dictionaries 'rows' based on a specific key.
    Args:
        rows (list): A list of dictionaries containing order data.
    Returns:
        list: A new sorted list with normalized values.
    """
    normalized_rows = copy.deepcopy(rows)
    for row in normalized_rows:
        if 'key1' not in row or row['key1'] is None:
            row['key1'] = ''
        if 'key2' not in row or row['key2'] is None:
            row['key2'] = ''
    normalized_rows.sort(key=lambda x: (x['key1'], x['key2']))
    return normalized_rows
if __name__ == "__main__":
    test_data = [{'key1': ''}, {'key1': 'value1', 'key2': 'value2'}, {'key2': 'value3'}]
    sorted_data = normalize_and_sort_orders(test_data)
    print(sorted_data)"""
caminho_alvo = "fixture/src/orders.py"
os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)
with open(caminho_alvo, "w", encoding="utf-8") as f:
    f.write(conteudo_corrigido)
print("[INFO] Arquivo orders.py reescrito diretamente com sucesso de forma garantida.")