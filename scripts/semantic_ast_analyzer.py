"""
AST Semantic Analyzer per NK TAS 3.0 / CRV 3.0 (GATE 4).
Genera il code_structure_map.json con Dependency Graph, estrazione docstring,
Dead Code Detection e Complessità Ciclomatica per funzione.
"""

import sys
import json
import ast
import os


class CyclomaticVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.complexity += 1
        self.generic_visit(node)


def analyze_semantic_ast(file_path: str) -> dict:
    """
    Analizza la struttura semantica dell'AST di un file Python.
    """
    if not os.path.exists(file_path):
        return {"status": "ERROR", "message": f"File non trovato: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as se:
        return {"status": "SYNTAX_ERROR", "message": str(se), "line": se.lineno}
    except Exception as e:
        return {"status": "ERROR", "message": f"Impossibile parsare l'AST: {str(e)}"}

    imports = []
    functions = []
    classes = []
    called_functions = set()
    defined_function_names = set()

    # Visitor per estrarre funzioni, classi e chiamate
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}" if mod else alias.name)

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_functions.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_functions.add(node.func.attr)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            class_methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            docstring = ast.get_docstring(node) or ""
            classes.append({
                "name": node.name,
                "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
                "methods": class_methods,
                "docstring": docstring[:150] if len(docstring) > 150 else docstring,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno)
            })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_function_names.add(node.name)
            v = CyclomaticVisitor()
            v.visit(node)
            docstring = ast.get_docstring(node) or ""
            params = [arg.arg for arg in node.args.args]
            
            functions.append({
                "name": node.name,
                "params": params,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "docstring": docstring[:150] if len(docstring) > 150 else docstring,
                "cyclomatic_complexity": v.complexity,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno)
            })

    # Rilevamento Dead Code (funzioni definite ma mai chiamate e non main/handler)
    dead_functions = [
        fn["name"] for fn in functions
        if fn["name"] not in called_functions 
        and not fn["name"].startswith("__") 
        and fn["name"] not in ("main", "run", "handler")
    ]

    total_complexity = sum(fn["cyclomatic_complexity"] for fn in functions)
    avg_complexity = round(total_complexity / len(functions), 2) if functions else 1.0
    max_complexity = max((fn["cyclomatic_complexity"] for fn in functions), default=1)

    return {
        "status": "SUCCESS",
        "file_scanned": file_path,
        "dependency_graph": {
            "imports": list(set(imports)),
            "imported_count": len(set(imports))
        },
        "classes": classes,
        "functions": functions,
        "dead_code": {
            "uncalled_functions": dead_functions,
            "dead_code_count": len(dead_functions)
        },
        "metrics": {
            "total_classes": len(classes),
            "total_functions": len(functions),
            "avg_cyclomatic_complexity": avg_complexity,
            "max_cyclomatic_complexity": max_complexity,
            "dead_code_count": len(dead_functions)
        }
    }


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        target = sys.argv[1]
        res = analyze_semantic_ast(target)
        print(json.dumps(res, indent=2))
    else:
        print(json.dumps({"status": "INFO", "usage": "python semantic_ast_analyzer.py path/to/file.py"}))
