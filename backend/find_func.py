import ast
with open("d:/Cloud Cost Management/backend/services/ml_predictor.py", "r", encoding="utf-8") as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        print(node.name)
