import os
import ast

def scan_files():
    found_missing = False
    for root, dirs, files in os.walk('.'):
        if 'api' in root.split(os.sep):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        try:
                            tree = ast.parse(f.read())
                        except SyntaxError:
                            continue
                        
                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):
                                # Check if it has a FastAPI decorator
                                is_route = False
                                for decorator in node.decorator_list:
                                    # Handle both @router.get() and @app.get() styles
                                    if isinstance(decorator, ast.Call):
                                        attr = decorator.func
                                        if isinstance(attr, ast.Attribute) and attr.attr in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                                            is_route = True
                                            break
                                
                                if is_route:
                                    docstring = ast.get_docstring(node)
                                    if not docstring:
                                        print(f"{filepath}: {node.name}")
                                        found_missing = True
    if not found_missing:
        print("All handlers are documented.")

if __name__ == "__main__":
    scan_files()
