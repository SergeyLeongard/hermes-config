import json
import os
from collections import defaultdict

INPUT = os.path.expanduser('~/.hermes/skills/manageengine-fsm/kb_categorized.json')
OUTPUT = os.path.expanduser('~/.hermes/skills/manageengine-fsm/graph.json')

def build_category_graph():
    with open(INPUT, 'r', encoding='utf-8') as f:
        requests = json.load(f)
    
    nodes = []
    edges = []
    
    # 1. Узлы заявок (только с категорией, чтобы не засорять)
    cat_map = defaultdict(list) # category -> [req_ids]
    
    for req in requests:
        cat = req.get("derived_category")
        req_id = f"req_{req.get('id', '0')}"
        
        # Добавляем заявку в узлы, только если у нее есть категория
        if cat:
            cat_map[cat].append(req_id)
            nodes.append({
                "id": req_id,
                "label": (req.get("subject") or "No Subject")[:25],
                "title": f"<b>{req.get('subject', '')}</b><br>{req.get('description', '')[:200]}...",
                "group": "request",
                "category": cat
            })
            
    # 2. Узлы категорий
    colors = {
        "Принтер/МФУ": "#3498db",
        "1С": "#e74c3c",
        "Компьютер/Железо": "#2ecc71",
        "Сеть/Интернет": "#f39c12",
        "ПО/Софт": "#9b59b6",
        "Почта": "#1abc9c",
        "Безопасность": "#e67e22",
        "Телефония": "#34495e"
    }
    
    for cat, req_ids in cat_map.items():
        cat_id = f"cat_{cat}"
        nodes.append({
            "id": cat_id,
            "label": cat,
            "group": "category",
            "title": f"Категория: {cat}<br>Заявок: {len(req_ids)}",
            "color": colors.get(cat, "#95a5a6"),
            "size": 20 + len(req_ids) * 0.5
        })
        # Связи заявка -> категория
        for rid in req_ids:
            edges.append({"from": rid, "to": cat_id, "arrows": "to"})
            
    # 3. Узел "Без категории" (для остальных)
    no_cat_reqs = [f"req_{r.get('id', '0')}" for r in requests if not r.get("derived_category")]
    if no_cat_reqs:
        nodes.append({
            "id": "cat_uncategorized",
            "label": "Без категории",
            "group": "category",
            "title": f"Заявок без категории: {len(no_cat_reqs)}",
            "color": "#bdc3c7",
            "size": 20 + len(no_cat_reqs) * 0.5
        })
        for rid in no_cat_reqs:
             edges.append({"from": rid, "to": "cat_uncategorized", "arrows": "to", "dashes": True})
             
    graph = {"nodes": nodes, "edges": edges}
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Граф обновлен: {OUTPUT}")
    print(f"   Узлов: {len(nodes)}")
    print(f"   Связей: {len(edges)}")
    print(f"   Категорий: {len(cat_map)}")

if __name__ == "__main__":
    build_category_graph()
